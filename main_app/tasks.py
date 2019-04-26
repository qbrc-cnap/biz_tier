import imaplib
import email
import ssl
import re
import bs4

from django.conf import settings
from celery.decorators import task

from helpers.email_utils import notify_admins, send_email

from main_app.models import ProcessedEmail, ResearchGroup


class MailQueryException(Exception):
    pass

class MailQueryWarning(Exception):
    pass

class MailParseException(Exception):
    pass


# these are keys required to be sent in the account request email:
REQUIRED_ACCOUNT_CREATION_KEYS = ['FIRST_NAME', \
    'LAST_NAME', \
    'EMAIL', \
    'PHONE', \
    'PI', \
    'PI_FIRST_NAME', \
    'PI_LAST_NAME', \
    'PI_EMAIL', \
    'PI_PHONE', \
    'HARVARD_APPOINTMENT', \
    'ORGANIZATION', \
    'DEPARTMENT', \
    'FINANCIAL_CONTACT', \
    'FINANCIAL_EMAIL', \
    'ADDRESS', \
    'CITY', \
    'STATE', \
    'POSTAL_CODE', \
    'COUNTRY'
]

def handle_exception(ex, message = ''):
    '''
    This function handles ...
    '''
    subject = 'Error encountered'
    if len(message) == 0:
        message = str(ex)
    notify_admins(message, subject)


def is_new_email(mail_server, folder, email_uid):
    '''
    Queries our database to see if this is a new email that we have not previously processed
    Returns True/False
    '''
    p = ProcessedEmail.objects.filter(
        mail_server_name = mail_server,
        mail_folder_name = folder,
        message_uid = email_uid
    )
    return len(p) == 0


def parse_account_creation_email(payload):
    '''
    Parses the email payload and returns a dictionary
    '''
    bs = bs4.BeautifulSoup(payload, 'html.parser')
    try:
        body_markup = bs.find_all('body')[0]
    except Exception as ex:
        raise MailParseException('Could not find a body section in the payload: %s' % payload)
    info_dict = {}
    contents = [x.strip() for x in body_markup.text.split('\n') if len(x.strip()) > 0]
    for x in contents:
        key, val = x.strip().split(':', 1) # only split on first colon, since there could be a colon in the response
        key = key.strip()
        val = val.strip()
        if key in REQUIRED_ACCOUNT_CREATION_KEYS:
            info_dict[key] = val
    if len(set(REQUIRED_ACCOUNT_CREATION_KEYS).difference(info_dict.keys())) > 0:
        raise MailParseException('Required information was missing in the email sent for account creation.')
    return info_dict


def process_single_email(message_uid, message):

    # prior to processing this email, mark it so we don't parse it again in case things take a while and
    # another mail query is performed:
    p = ProcessedEmail.objects.create(
        mail_server_name = settings.MAIL_HOST,
        mail_folder_name = settings.MAIL_FOLDER_NAME,
        message_uid = message_uid
    )
    p.save()

    try:
        m = email.message_from_string(message[1].decode('utf-8'))
        body_html = m.get_payload()
        info_dict = parse_account_creation_email(payload)
        return info_dict
    except Exception as ex:
        # if anything went wrong, we do not want to accidentally mark this email
        # as processed, so delete the database object:
        p.delete()
        raise ex

def fetch_emails(mail, id_list):
    '''
    Queries the mail server for the messages corresponding to the 
    UIDs in id_list.

    Returns a list
    '''
    # have to turn the id list into a csv of integers:
    id_csv = ','.join(id_list)
    status, messages = mail.fetch(id_csv, '(BODY.PEEK[])')
    if status != 'OK':
        raise MailQueryException('Failed when fetching messages.')
    return messages

def check_for_pi_account(info_dict):
    '''
    Looks into the database and returns bool indicating whether
    we "know about" this PI
    '''
    pi_email = info_dict['PI_EMAIL']

    try:
        research_group = ResearchGroup.objects.get(pi_email = pi_email)
        return True
    except ResearchGroup.DoesNotExist:
        # we do not know who this PI is!
        return False

def handle_unknown_pi_account(info_dict, is_pi_request):
    '''
    This function handles the business logic when a request
    contains PI info that we do not recognize.  See comments below
    for additional logic in this situation.

    info_dict is a dictionary of information parsed from the email
    is_pi_request is a bool indicating whether the account request
    is for themself, as opposed to another user attempting to register
    an account with someone else listed as their PI
    '''


def handle_request_email(info_dict):
    '''
    This contains our business logic for account creation.  info_dict
    is a dictionary containing information parsed from the request email
    sent by qualtrics survey
    '''
    is_pi_str = info_dict['PI']
    if is_pi_str.lower() == 'no':
        pi_request = True
    else:
        pi_request = False

    pi_account_exists = check_for_pi_account(info_dict)

    if not pi_account_exists:
        handle_unknown_pi_account(info_dict, pi_request)

    

def process_emails(mail, id_list):
    '''
    Actually grabs the emails from the server

    mail is an instance of imaplib.IMAP4_SSL
    id_list is a list of integers.  Each integer 
    is a UID of an email that matched our query.  It should be a list of 
    UIDs that we have not already checked.
    '''
    # go get the messages.  It is a list of where the odd indexes are byte strings (useless for our purposes here)
    # and the even-numbered indexes have tuples.
    messages = fetch_emails(mail, id_list)

    # As mentioned above, the even indexes have tuples.  The mail body itself is contained in the second
    # slot in the tuple
    for uid, message in zip(id_list, messages[::2]):
        try:
            info_dict = process_single_email(uid, message)

            # call the logic for account creation
            handle_request_email(info_dict)

        except Exception as ex:
            # handle each email error individually.  This way a single
            # error does not block other requests that are correct.
            handle_exception(ex)



def query_imap_server_for_ids(mail):
    '''
    Queries IMAP server for messages.  Returns a list of integers which
    are unique IDs.

    Queries by searching for a matching subject
    '''
    status, response = mail.search(None, '(TO "qbrc@hsph.harvard.edu") (SUBJECT "CNAP Account Request")')
    if status != 'OK':
        raise MailQueryException('The mailbox search did not succeed.')

    # response is something like: [b'749 753 754 755 784 785 786 787 788 789 790']
    # or [b'']

    # warn the admins- it is quite unlikely that there will be ZERO messages
    # matching our query.  Not strictly an error, but a warning
    if len(response[0]) == 0:
        raise MailQueryWarning('Empty query response from IMAP server.')

    try:
        id_list = [int(x) for x in response[0].decode('utf-8').split(' ')]
        return id_list
    except Exception as ex:
        raise MailQueryException('Could not parse the response from imap server: %s' % response)


def get_mailbox():
    '''
    Sets up the connection and returns a mailbox (an instance of imaplib.IMAP4_SSL)
    '''
    context = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
    try:
        mail = imaplib.IMAP4_SSL(settings.MAIL_HOST, settings.MAIL_PORT, ssl_context=context)
    except Exception as ex:
        raise MailQueryException('Could not reach imap server at %s:%d.  Reason was: %s' % (settings.MAIL_HOST, settings.MAIL_PORT, str(ex)))
    try:
        status, msg = mail.login(settings.MAIL_USERNAME, settings.MAIL_PASSWORD)
        if status != 'OK':
            raise MailQueryException(msg[0].decode('utf-8'))
    except Exception as ex:
        raise MailQueryException('Could not login to imap server.  Reason was: %s' % str(ex))
   
    try: 
        mail.select(settings.MAIL_FOLDER_NAME, readonly=True)
    except Exception as ex:
        raise MailQueryException('Could not select INBOX.  Reason was: %s' % str(ex))
    return mail


@task(name='check_for_qualtrics_survey_results')
def check_for_qualtrics_survey_results():
    '''
    Queries the imap server to check for survey results sent by the qualtrics
    application.
    '''

    # if something fails during this block, just block future
    try:
        mail = get_mailbox()
        id_list = query_imap_server_for_ids(mail)
        unprocessed_uids = [uid for uid in id_list if is_new_email(settings.MAIL_HOST, settings.MAIL_FOLDER_NAME, uid)]
        
        # if we get here, then the connection and initial email query completed succesfully.
        # The process_emails function handles exceptions on each email individually (and handles 
        # those individual exceptions) so bad requests do not block potentiall valid ones
        process_emails(mail, unprocessed_uids)
    except Exception as ex:
        # This should catch any exceptions raised prior to the point at which we
        # start processing individual emails
        handle_exception(ex)