import imaplib
import email
import ssl
import re
import bs4
import json
import hashlib
import uuid
import requests

from django.conf import settings
from django.urls import reverse
from django.contrib.sites.models import Site
from django.contrib.auth import get_user_model

from celery.decorators import task

from helpers.email_utils import notify_admins, send_email

from main_app.models import ProcessedEmail, \
    ResearchGroup, \
    PendingUser, \
    Organization, \
    FinancialCoordinator, \
    CnapUser, \
    Payment, \
    Budget, \
    Product, \
    Order, \
    Purchase

class MailQueryException(Exception):
    pass

class MailQueryWarning(Exception):
    pass

class MailParseException(Exception):
    pass

class InventoryException(Exception):
    pass

class ProductDoesNotExistException(Exception):
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

REQUIRED_PIPELINE_CREATION_KEYS = {
    'REGISTERED',
    'EMAIL',
    'PI_EMAIL',
    'HAVE_ACCT_NUM',
    'ACCT_NUM',
    'NUM_OF_SAMPLE',
    'PIPELINE',
    'SEQ_TYPE'
}

# flags for common reference
ACCOUNT_REQUEST = 'account request'
PIPELINE_REQUEST = 'pipeline request'

def send_self_approval_email_to_pi(pending_user_instance):
    '''
    This function constructs the email that is sent to the PI
    when they themselves have requested an account for themself

    Requiring an approval link keeps others from spoofing their PI
    '''

    user_info = json.loads(pending_user_instance.info_json)
    pi_email = user_info['PI_EMAIL']
    approval_url = reverse('pi_account_approval', args=[pending_user_instance.approval_key,])
    current_site = Site.objects.get_current()
    domain = current_site.domain
    full_url = 'https://%s%s' % (domain, approval_url)
    subject = '[CNAP] New account confirmation'
    plaintext_msg = '''
        A new account was requested, which listed your email as the principal investigator. 
        The information we collected was:
        -------------------------------------
        %s
        -------------------------------------
        Click the following link (or copy/paste into a browser) to approve this: %s

        If you do not approve this request, you do not need to do anything.  No accounts
        are created without proper confirmation.

        - qBRC Team (qbrc@hsph.harvard.edu)
    ''' % (json.dumps(user_info), full_url)

    message_html = '''
        <html>
        <body>
        <p>A new account was requested, which listed your email as the principal investigator.</p>
        <p>The information we collected was</p>
        <hr>
        <pre>
        %s
        </pre>
        <hr>
        <p>Click <a href="%s">here</a> to approve this request. </p>

        <p>If you do not approve this request, you do not need to do anything.  No accounts
        are created without proper confirmation.</p> 

        <p>qBRC Team <a href="mailto:qbrc@hsph.harvard.edu">qbrc@hsph.harvard.edu</a></p>
        </body>
        </html>
    ''' % (json.dumps(user_info), full_url)
    send_email(plaintext_msg, message_html, pi_email, subject)


def send_approval_email_to_pi(pending_user_instance):
    '''
    This function constructs the email that is sent to the PI
    when someone else has listed them as a PI
    '''

    user_info = json.loads(pending_user_instance.info_json)
    pi_email = user_info['PI_EMAIL']
    approval_url = reverse('pi_account_approval', args=[pending_user_instance.approval_key,])
    current_site = Site.objects.get_current()
    domain = current_site.domain
    full_url = 'https://%s%s' % (domain, approval_url)
    subject = '[CNAP] New account confirmation'
    requesting_user_firstname = user_info['FIRST_NAME']
    requesting_user_lastname = user_info['LAST_NAME']
    requesting_user_email = user_info['EMAIL']

    plaintext_msg = '''
        A new account was requested, which listed your email as the principal investigator.  The requesting
        user was:
        -------------------------------------
        %s %s (%s)
        -------------------------------------
        Click the following link (or copy/paste into a browser) to approve this: %s

        If you do not approve this request, you do not need to do anything.  No accounts
        are created without proper authorization by the principal investigator.

        - qBRC Team (qbrc@hsph.harvard.edu)
    ''' % (requesting_user_firstname, requesting_user_lastname, requesting_user_email, full_url)

    message_html = '''
        <html>
        <body>
        <p>A new account was requested, which listed your email as the principal investigator.</p>
        <p>The information we collected was</p>
        <hr>
        <p>%s %s (%s)<p>
        <hr>
        <p>Click <a href="%s">here</a> to approve this request. </p>

        <p>If you do not approve this request, you do not need to do anything.  No accounts
        are created without proper authorization by the principal investigator.</p> 

        <p>qBRC Team <a href="mailto:qbrc@hsph.harvard.edu">qbrc@hsph.harvard.edu</a></p>
        </body>
        </html>
    ''' % (requesting_user_firstname, requesting_user_lastname, requesting_user_email, full_url)

    send_email(plaintext_msg, message_html, pi_email, subject)


def send_account_pending_email_to_requester(pending_user_instance):
    '''
    This sends a message to a user who has requested an account, but lists someone
    else as the PI.  We let them know that the PI has to still approve
    ''' 
    user_info = json.loads(pending_user_instance.info_json)
    pi_email = user_info['PI_EMAIL']
    subject = '[CNAP] Notification: account pending'
    requesting_user_email = user_info['EMAIL']

    plaintext_msg = '''
        This email is to let you know that your account request has been approved by the QBRC staff,
        but still requires approval of the principal investigator you have listed (%s).  The PI 
        has also been notified of this request.
        
        Until approval is granted by the PI, your request will be pending.  No accounts are created 
        without proper authorization by the principal investigator.

        qBRC Team (qbrc@hsph.harvard.edu)
    ''' % (pi_email)

    message_html = '''
        <html>
        <body>
        <p>
        This email is to let you know that your account request has been approved by the QBRC staff,
        but still requires approval of the principal investigator you have listed (%s).  The PI 
        has also been notified of this request.
        </p>

        <p>Until approval is granted by the PI, your request will be pending.  No accounts are created 
        without proper authorization by the principal investigator.</p> 

        <p>qBRC Team <a href="mailto:qbrc@hsph.harvard.edu">qbrc@hsph.harvard.edu</a></p>
        </body>
        </html>
    ''' % (pi_email)

    send_email(plaintext_msg, message_html, requesting_user_email, subject)


def send_account_confirmed_email_to_requester(pending_user_instance):
    '''
    This sends a message to a user who has requested an account once
    the PI has approved the request
    ''' 
    user_info = json.loads(pending_user_instance.info_json)
    pi_email = user_info['PI_EMAIL']
    subject = '[CNAP] New account created'
    requesting_user_email = user_info['EMAIL']

    plaintext_msg = '''
        This email is to let you know that your account request has been approved by your
        principal investigator you have listed (%s).  You may now request analysis projects
        on the CNAP platform.

        qBRC Team (qbrc@hsph.harvard.edu)
    ''' % (pi_email)

    message_html = '''
        <html>
        <body>
        <p>
        This email is to let you know that your account request has been approved by your
        principal investigator you have listed (%s).  You may now request analysis projects
        on the CNAP platform
        </p>

        <p>qBRC Team <a href="mailto:qbrc@hsph.harvard.edu">qbrc@hsph.harvard.edu</a></p>
        </body>
        </html>
    ''' % (pi_email)

    send_email(plaintext_msg, message_html, requesting_user_email, subject)


def send_account_confirmed_email_to_qbrc(pending_user_instance):
    '''
    This sends a message to the QBRC once
    the PI has approved the request
    ''' 
    user_info = json.loads(pending_user_instance.info_json)
    pi_email = user_info['PI_EMAIL']
    subject = '[CNAP] New account created'
    requesting_user_email = user_info['EMAIL']

    plaintext_msg = '''
        The following account has been approved by the PI (%s):

        %s %s (%s)
        
    ''' % (pi_email, user_info['FIRST_NAME'], user_info['LAST_NAME'], requesting_user_email)

    message_html = '''
        <html>
        <body>
        <p>
        The following account has been approved by the PI (%s):
        </p>
        <hl>
        <p>
        %s %s (%s)
        </p>
        <hl>
        </body>
        </html>
    ''' % (pi_email, user_info['FIRST_NAME'], user_info['LAST_NAME'], requesting_user_email)

    send_email(plaintext_msg, message_html, settings.QBRC_EMAIL, subject)


def instantiate_new_research_group(info_dict):
    '''
    This is called following approval by the PI-- if the PI does not have an existing
    ResearchGroup, then we end up here.
    '''
    org = None
    if len(info_dict['ORGANIZATION']) > 0:
        org = Organization.objects.create(name = info_dict['ORGANIZATION'])

    # create a ResearchGroup lead by this PI:
    rg = ResearchGroup.objects.create(
        organization = org,
        pi_email = info_dict['PI_EMAIL'],
        pi_name = '%s %s' % (info_dict['PI_FIRST_NAME'], info_dict['PI_LAST_NAME']),
        has_harvard_appointment = True if info_dict['HARVARD_APPOINTMENT'].lower() == 'y' else False,
        department = info_dict['DEPARTMENT'],
        address_lines = info_dict['ADDRESS'],
        city = info_dict['CITY'],
        state = info_dict['STATE'],
        postal_code = info_dict['POSTAL_CODE'],
        country = info_dict['COUNTRY']
    )
    rg.save()

    # create a financial contact
    fc = FinancialCoordinator.objects.create(
        contact_name = info_dict['FINANCIAL_CONTACT'],
        contact_email = info_dict['FINANCIAL_EMAIL'],
        research_group = rg
    )
    fc.save()

    # regardless of the request, create a user representing this PI:
    pi_user_obj = get_user_model().objects.create(
        first_name = info_dict['PI_FIRST_NAME'],
        last_name = info_dict['PI_LAST_NAME'],
        email = info_dict['PI_EMAIL']
    )
    pi_user_obj.save()

    # above that created a regular Django user instance.  We also create a CnapUser instance, which
    # lets us associate the user with a research group
    cnap_user = CnapUser.objects.create(user=pi_user_obj)
    cnap_user.research_group.add(rg)
    cnap_user.save()

    return rg


@task(name='pi_approve_pending_user')
def pi_approve_pending_user(pending_user_pk):
    '''
    The PI has authorized the account.  This function is directly called when a PI approves
    an account, so it handles situations where the research group does not exist and situations
    where new accounts are requested for an existing research group
    '''
    # get the PendingUser instance:
    p = PendingUser.objects.get(pk=pending_user_pk)
    info_dict = json.loads(p.info_json)
    is_pi = p.is_pi

    # does this group already exist?
    rg = check_for_pi_account(info_dict)

    # if the group does not exist, create it, including the PI
    if not rg:
        rg = instantiate_new_research_group(info_dict)

    # if the request was made by someone other than the PI, create a user
    # instance for that person
    if not is_pi:
        # check if the user already exists.  This can be the case if
        # an existing user goes to another lab where the PI did not have 
        # a CNAP account.  In this case, we already know of the 'regular'
        # user.
        try:
            user_obj = get_user_model().objects.get(email = info_dict['EMAIL'])
        except Exception:
            # a user with that email was not found.  Create a new basic user instance
            user_obj = get_user_model().objects.create(
                first_name = info_dict['FIRST_NAME'],
                last_name = info_dict['LAST_NAME'],
                email = info_dict['EMAIL']
            )
            user_obj.save()

        # above that created or queried a regular Django user instance.  We also create a CnapUser instance, which
        # lets us associate the user with a research group
        # First see if this association has already been made, perhaps through repeated requests
        # and the failure of the PI to confirm in a timely fashion
        try:
            CnapUser.objects.get(user=user_obj, research_group = rg)
            # if we are here, then the CnapUser already existed and we do nothing.
            # The only conceivable way to get here is if someone issues multiple account
            # requests (thus sending the PI multiple requests) and then the PI confirms
            # all of those requests.
        except CnapUser.DoesNotExist:
            cnap_user = CnapUser.objects.create(user=user_obj)
            cnap_user.research_group.add(rg)
            cnap_user.save()

            # Let this user know their PI has approved the request.
            send_account_confirmed_email_to_requester(p)

            # Let the QBRC know we have a new account confirmed:
            send_account_confirmed_email_to_qbrc(p)

    # at this point we can remove the PendingUser:
    #TODO: do we delete, or mark 'invative'?
    #p.delete()


def add_approval_key_to_pending_user(pending_user_instance):
    # generate a random key which will be used as part of the link sent to the PI.  When the PI clicks on that, it will
    # allow us to reference the PendingUser obj
    info_dict = json.loads(pending_user_instance.info_json)
    salt = uuid.uuid4().hex
    s = (info_dict['PI_EMAIL'] + salt).encode('utf-8')
    approval_key = hashlib.sha256(s).hexdigest()
    pending_user_instance.approval_key = approval_key
    pending_user_instance.save()


@task(name='staff_approve_pending_user')
def staff_approve_pending_user(pending_user_pk):
    '''
    A staff member has indicated that this pending user should be approved for use of CNAP.  Start the downstream processes.
    '''

    # get the PendingUser instance:
    p = PendingUser.objects.get(pk=pending_user_pk)
    info_dict = json.loads(p.info_json)
    is_pi = p.is_pi

    # generate an approval key:
    add_approval_key_to_pending_user(p)

    # if it was a request by the PI, we simply let them know their request was approved.
    # Note that they still have to approve by clicking in an email-- otherwise anyone could spoof their PI
    if is_pi:
        send_self_approval_email_to_pi(p)

    # if the request was made by a 'regular' user, and they listed an unknown PI, we need to first
    # get approval of the PI.  Send email to PI asking for approval and send email to client telling them 
    # that the request is pending their PI's approval.
    else:
        send_approval_email_to_pi(p)
        send_account_pending_email_to_requester(p)



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


def parse_email_contents(payload, required_keyset):
    '''
    Parses the email payload for an account request and returns a dictionary
    '''
    bs = bs4.BeautifulSoup(payload, 'html.parser')
    try:
        body_markup = bs.find_all('body')[0]
    except Exception as ex:
        raise MailParseException('Could not find a body section in the payload: %s' % payload)
    info_dict = {}
    contents = [x.strip() for x in body_markup.text.split('\n') if len(x.strip()) > 0]
    for x in contents:
        try:
            key, val = x.strip().split(':', 1) # only split on first colon, since there could be a colon in the response
        except ValueError as ex:
            raise MailParseException('Email parse error.  Encountered problem with this line: %s' % x)
        key = key.strip()
        val = val.strip()
        if key in required_keyset:
            info_dict[key] = val
    if len(set(required_keyset).difference(info_dict.keys())) > 0:
        raise MailParseException('Required information was missing in the email sent for account creation.')
    return info_dict


def get_email_body(message_uid, message):

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
        return m.get_payload()

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
    id_csv = ','.join([str(x) for x in id_list])
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
        return ResearchGroup.objects.get(pi_email = pi_email)
    except ResearchGroup.DoesNotExist:
        # we do not know who this PI is!
        return None


def inform_staff_of_new_account(pending_user):

    user_info = json.loads(pending_user.info_json)
    approval_url = reverse('staff_account_approval', args=[pending_user.pk,])
    current_site = Site.objects.get_current()
    domain = current_site.domain
    full_url = 'https://%s%s' % (domain, approval_url)
    subject = '[CNAP] New account request'
    plaintext_msg = '''
        A new account request was received:
        -------------------------------------
        %s
        -------------------------------------
        Go to this link to approve: %s
    ''' % (json.dumps(user_info), full_url)

    message_html = '''
        <html>
        <body>
        <p>A new account request was received:</p>
        <hr>
        <pre>
        %s
        </pre>
        <hr>
        Go <a href="%s">here</a> to approve.
        </body>
        </html>
    ''' % (json.dumps(user_info), full_url)
    send_email(plaintext_msg, message_html, settings.QBRC_EMAIL, subject)


def handle_unknown_pi_account(info_dict, is_pi_request):
    '''
    This function handles the business logic when a request
    contains PI info that we do not recognize.  See comments below
    for additional logic in this situation.

    info_dict is a dictionary of information parsed from the email
    is_pi_request is a bool indicating whether the account request
    is for themself, as opposed to another user attempting to register
    an account (with someone else listed as their PI)
    '''
    
    # create a PendingUser:
    # Note that all the request info is placed into the info_json field, so we can
    # resolve the creation of regular users and PI later on
    p = PendingUser.objects.create(is_pi = is_pi_request, info_json = json.dumps(info_dict))
    p.save()

    # inform our staff about this request so we can review before allowing
    # them to proceed further.
    inform_staff_of_new_account(p) 


def inform_user_of_existing_account(info_dict):
    '''
    This function is triggered if we receive an account request from the 
    PI themself but we already know of them.  Simply remind them
    '''
    current_site = Site.objects.get_current()
    domain = current_site.domain
    subject = '[CNAP] Duplicate account request received'
    plaintext_msg = '''
        A new account request for CNAP was received for your email.  We already have an account
        with that email associated with your designated PI, so no action has been performed.

        qBRC Team (qbrc@hsph.harvard.edu)
    '''

    message_html = '''
        <html>
        <body>
        <p>        
        A new account request for CNAP was received for your email.  We already have an account
        with that email associated with your designated PI, so no action has been performed.</p>
        <p>qBRC Team <a href="mailto:qbrc@hsph.harvard.edu">qbrc@hsph.harvard.edu</a></p>
        </body>
        </html>
    '''

    send_email(plaintext_msg, message_html, settings.QBRC_EMAIL, subject)


def determine_if_existing_user(info_dict):
    '''
    Detemines whether this user already existed in our system
    Note that it looks at the 'base' user object. NOT the CnapUser
    '''
    try:
        return get_user_model().objects.get(email=info_dict['EMAIL'])
    except Exception as ex:
        return None


def handle_account_request_for_existing_user(info_dict, existing_user, pi_request, research_group):
    '''
    This covers the case where we know about a particular user.  Depending on the PI status
    we do a few different things
    '''

    if not research_group:
        handle_unknown_pi_account(info_dict, pi_request)
    else:
        # we have an existing user and an existing group.  Are they already associated?
        # the case where there is an existing research group and it's the PI who is making
        # the request is handled elsewhere.  Thus, the existing user here is a "regular" user
        # not a PI
        try:
            c = CnapUser.objects.get(user=existing_user, research_group=research_group)

            # if we are here, we have the case where an existing user who is already associated
            # with this lab has repeated their request.  Simply email them to let them know
            # they already have an account.
            inform_user_of_existing_account(info_dict)

        except CnapUser.DoesNotExist:
            # was not found, so the existing user was not previously associated with the existing
            # ResearchGroup.  Need to have the PI confirm this association.
            p = PendingUser.objects.create(is_pi = False, info_json = json.dumps(info_dict))
            p.save()
            add_approval_key_to_pending_user(p)

            # now send the email with the confirmation link.
            send_approval_email_to_pi(p)


def handle_account_request_for_new_user(info_dict, pi_request, research_group):
    '''
    If the user did not previously exist.  PI may or may not exist
    '''
    if not research_group:
        handle_unknown_pi_account(info_dict, pi_request)
    else: # PI account exists
        # We first ask for the PI to validate this activity
        # We must first create a PendingUser and generate an approval key.
        p = PendingUser.objects.create(is_pi = False, info_json = json.dumps(info_dict))
        p.save()
        add_approval_key_to_pending_user(p)

        # now send the email with the confirmation link.
        send_approval_email_to_pi(p)

        # let the requester know that they are waiting on the PI 
        # to approve
        send_account_pending_email_to_requester(p)


def handle_account_request_email(info_dict):
    '''
    This contains our business logic for account creation.  info_dict
    is a dictionary containing information parsed from the request email
    sent by qualtrics survey
 
    '''

    # do we know of this user?  Whether the request was from a PI or a regular
    # user, this query is applicable.
    existing_user = determine_if_existing_user(info_dict)
    is_pi_str = info_dict['PI']
    if is_pi_str.lower()[0] == 'y':
        pi_request = True
    else:
        pi_request = False

    # simply checks if the PI has an existing research group.  Does not look at
    # whether the requester was previously associated with that group
    research_group = check_for_pi_account(info_dict)

    if pi_request and research_group:
        # they simply forgot-- email to let them know they have an account already
        inform_user_of_existing_account(info_dict)
        return

    # we now have info about whether this user previously existed AND whether
    # there is a ResearchGroup for the PI.
    if existing_user:
        handle_account_request_for_existing_user(info_dict, existing_user, pi_request, research_group)
    else:
        handle_account_request_for_new_user(info_dict, pi_request, research_group)
    

def ask_requester_to_register_first(email):
    '''
    This sends a message to a user who has requested an pipeline, but is unknown to us
    ''' 

    subject = '[CNAP] Your pipeline request'

    plaintext_msg = '''
        This email is to let you know that your pipeline request was denied since you have not registered an active account with 
        us.  Please fill out the account request first.
        
        qBRC Team (qbrc@hsph.harvard.edu)
    '''

    message_html = '''
        <html>
        <body>
        <p>
        This email is to let you know that your pipeline request was denied since you have not registered an active account with 
        us.  Please fill out the account request first.
        </p>

        <p>qBRC Team <a href="mailto:qbrc@hsph.harvard.edu">qbrc@hsph.harvard.edu</a></p>
        </body>
        </html>
    '''

    send_email(plaintext_msg, message_html, email, subject)


def ask_requester_to_associate_with_pi_first(info_dict):
    '''
    This messages a user who is requesting a pipeline.  We know about this user, but they are listing
    a PI who they have not previously associated with.  This could be the case if someone switched labs.
    '''

    # at this point we only know that we know this user.  We have also found that they are not
    # associated with the PI given in their request.  HOWEVER, we have not checked that said PI
    # has an account in our system.  Depending on existence of the PI, we send different messages.

    pi_exists = check_for_pi_account(info_dict)

    if pi_exists:
        message = '''
            Although your email is known to our system, we do not have a record of this email being associated with the 
            principal investigator you listed (%s).  Please submit an account request so establish yourself as a member
            of this new group.
        ''' % info_dict['PI_EMAIL']
    else:
        message = '''
            Although your email is known to our system, we do not have a record of the 
            principal investigator you listed (%s).  Please submit an account request so establish yourself as a member
            of this new group.  This will require the PI to approve your request.
        ''' % info_dict['PI_EMAIL']

    subject = '[CNAP] Your pipeline request'

    plaintext_msg = '''
        %s

        qBRC Team (qbrc@hsph.harvard.edu)
    ''' % message

    message_html = '''
        <html>
        <body>
        <p>
        %s
        </p>

        <p>qBRC Team <a href="mailto:qbrc@hsph.harvard.edu">qbrc@hsph.harvard.edu</a></p>
        </body>
        </html>
    ''' % message

    send_email(plaintext_msg, message_html, info_dict['EMAIL'], subject)


def inform_qbrc_of_request_without_payment_number(info_dict):

    subject = '[CNAP] Pipeline request received without payment account'
    plaintext_msg = '''
        A new pipeline request was received that did not specify a payment account:
        -------------------------------------
        %s
        -------------------------------------
    ''' % json.dumps(info_dict)

    message_html = '''
        <html>
        <body>
        <p>A new pipeline request was received that did not specify a payment account:</p>
        <hr>
        <pre>
        %s
        </pre>
        <hr>
        </body>
        </html>
    ''' % json.dumps(info_dict)
    send_email(plaintext_msg, message_html, settings.QBRC_EMAIL, subject)


def inform_qbrc_of_bad_pipeline_request(info_dict):

    subject = '[CNAP] Pipeline request received for unknown pipeline'
    plaintext_msg = '''
        A new pipeline request was received that specified an unrecognized pipeline:
        -------------------------------------
        %s
        -------------------------------------
    ''' % json.dumps(info_dict)

    message_html = '''
        <html>
        <body>
        <p>A new pipeline request was received that specified an unrecognized pipeline:</p>
        <hr>
        <pre>
        %s
        </pre>
        <hr>
        </body>
        </html>
    ''' % json.dumps(info_dict)
    send_email(plaintext_msg, message_html, settings.QBRC_EMAIL, subject)


def calculate_total_purchase(info_dict):
    '''
    This calculates the total cost of a particular purchase and returns
    that number
    '''
    pipeline = info_dict['PIPELINE']
    quantity_ordered = int(info_dict['NUM_OF_SAMPLE'])

    # go find the product corresponding to this pipeline:
    try:
        product = Product.objects.get(name=pipeline)
    except Product.DoesNotExist:
        inform_qbrc_of_bad_pipeline_request(info_dict)
        raise ProductDoesNotExistException('')

    # should also check if this is limited in any way
    if product.is_quantity_limited:
        qty_available = product.quantity
        if quantity_ordered > qty_available:
            raise InventoryException('The quantity ordered (%d) was greater than the number available')
    # if we make it here, we either have unlimited product or the quantity ordered
    # was OK given our inventory
    return (quantity_ordered, product.unit_cost)


def send_inventory_alert_to_requester(info_dict):
    '''
    Lets the requester know that their request exceeded our inventory
    '''    
    subject = '[CNAP] Your pipeline request'

    plaintext_msg = '''
        This email is to let you know that your pipeline request was denied since the order exceeded
        our available inventory.  Please contact the QBRC to resolve this issue.

        qBRC Team (qbrc@hsph.harvard.edu)
    '''

    message_html = '''
        <html>
        <body>
        <p>
        This email is to let you know that your pipeline request was denied since the order exceeded
        our available inventory.  Please contact the QBRC to resolve this issue.
        </p>

        <p>qBRC Team <a href="mailto:qbrc@hsph.harvard.edu">qbrc@hsph.harvard.edu</a></p>
        </body>
        </html>
    '''

    send_email(plaintext_msg, message_html, info_dict['EMAIL'], subject)


def send_inventory_alert_to_qbrc(info_dict):
    '''
    Lets the QBRC know that someone has requested a pipeline that has
    exceeded our inventory
    '''

    subject = '[CNAP] Pipeline request-- inventory issue'
    plaintext_msg = '''
        A new pipeline request was received which exceeded our inventory:
        -------------------------------------
        %s
        -------------------------------------
    ''' % json.dumps(info_dict)

    message_html = '''
        <html>
        <body>
        <p>A new pipeline request was received which exceeded our inventory:</p>
        <hr>
        <pre>
        %s
        </pre>
        <hr>
        </body>
        </html>
    ''' % json.dumps(info_dict)
    send_email(plaintext_msg, message_html, settings.QBRC_EMAIL, subject)


def general_alert_to_requester(info_dict):
    '''
    A general alert sent to the pipeline requester
    '''    
    subject = '[CNAP] Your pipeline request'

    plaintext_msg = '''
        This email is to let you know that your pipeline request was denied due to an unexpected
        problem.  We are working to resolve this and will be in contact.

        qBRC Team (qbrc@hsph.harvard.edu)
    '''

    message_html = '''
        <html>
        <body>
        <p>
        This email is to let you know that your pipeline request was denied due to an unexpected
        problem.  We are working to resolve this and will be in contact.
        </p>

        <p>qBRC Team <a href="mailto:qbrc@hsph.harvard.edu">qbrc@hsph.harvard.edu</a></p>
        </body>
        </html>
    '''

    send_email(plaintext_msg, message_html, info_dict['EMAIL'], subject)

def handle_no_payment_number(info_dict):
    '''
    If a pipeline was requested, but the user did not specify an account number
    we end up here.
    '''
    # prepare some cost estimate:
    try:
        qty, unit_cost = calculate_total_purchase(info_dict)
        total_cost = qty * unit_cost
    except InventoryException as ex:
        send_inventory_alert_to_requester(info_dict)
        send_inventory_alert_to_qbrc(info_dict)
        return
    except ProductDoesNotExistException as ex:
        general_alert_to_requester(info_dict)
        return

    # message the user if we have made it this far-- the request
    # is otherwise fine
    subject = '[CNAP] Pipeline request-- more information needed'

    plaintext_msg = '''
        The pipeline request you have submitted was not associated with a known
        payment method.  The QBRC will be in contact with you to work out details.

        The order requested was:
        - %s (%d at $%.2f each)
        The total cost of the request is $%.2f

        qBRC Team (qbrc@hsph.harvard.edu)
    ''' % (info_dict['PIPELINE'], qty, unit_cost, total_cost)

    message_html = '''
        <html>
        <body>
        <p>The pipeline request you have submitted was not associated with a known
        payment method.  The QBRC will be in contact with you to work out details.</p>
        The order requested was:
        <ul>
        <li>
          %s (%d at $%.2f each)
        </li>
        </ul>
        <p>The total cost of the request is $%.2f</p>
        <p>qBRC Team <a href="mailto:qbrc@hsph.harvard.edu">qbrc@hsph.harvard.edu</a></p>
        </body>
        </html>
    ''' % (info_dict['PIPELINE'], qty, unit_cost, total_cost)
    send_email(plaintext_msg, message_html, info_dict['EMAIL'], subject)


def ask_user_to_resubmit_payment_info(info_dict):
    '''
    We end up here if the user has submitted a pipeline request and has provided
    a payment number that we cannot find. It is possible it was a typo, etc.
    so we let them know.
    '''
    # message the user
    subject = '[CNAP] Pipeline request-- payment account not found'

    plaintext_msg = '''
        The pipeline request you have submitted was not associated with a known
        payment method, according to our records.  Please check that you have typed
        the number correctly.  If you believe this is in error, please contact the QBRC.

        Provided payment number: %s

        qBRC Team (qbrc@hsph.harvard.edu)
    ''' % info_dict['ACCT_NUM']

    message_html = '''
        <html>
        <body>
        <p>The pipeline request you have submitted was not associated with a known
        payment method, according to our records.  Please check that you have typed
        the number correctly.  If you believe this is in error, please contact the QBRC.</p>

        <p>Provided payment number: %s</p>
        <p>qBRC Team <a href="mailto:qbrc@hsph.harvard.edu">qbrc@hsph.harvard.edu</a></p>
        </body>
        </html>
    ''' % info_dict['ACCT_NUM']

    send_email(plaintext_msg, message_html, info_dict['EMAIL'], subject)


def create_budget(payment_ref, current_sum = 0.0):
    '''
    Used to create Budget instances, e.g. in cases where there was none
    made previously
    '''

    budget = Budget.objects.create(
        payment=payment_ref, 
        current_sum =current_sum
    )
    budget.save()
    return budget


def check_that_purchase_is_valid_against_payment(info_dict, payment_ref):
    '''
    If this function is invoked, the user and account number are valid, but
    we still need to check that the purchase is OK given the potential budget, etc.

    Returns a tuple.  The first item is a bool indicating that the purchase is ok.
    The second gives a string, which can inform the user what was wrong
    with their purchase
    '''
    try:
        qty, unit = calculate_total_purchase(info_dict)
        total_cost = qty*unit
    except InventoryException as ex:
        send_inventory_alert_to_qbrc(info_dict)
        return (False, 'The requested order exceeded our inventory')
    except ProductDoesNotExistException as ex:
        return (False, 'An unexpected error occurred processing the order.  We are working to resolve this.')

    try:
        budget = Budget.objects.get(payment=payment_ref)
    except Budget.DoesNotExist:
        # If here, then there was obviously no Budget associated
        # with this Payment instance.  
        budget = create_budget(payment_ref)

    payment_amount = payment_ref.payment_amount
    if payment_amount:
        current_charges_against_payment = budget.current_sum
        new_sum = current_charges_against_payment + total_cost
        if new_sum > payment_amount:
            rejection_reason = '''
            The cost of the requested project exceeds the payment it is 
            billed against.  The total cost of the order (%d analyses at $%.2f each),
            when added to the prior charges ($%.2f), exceeded 
            the total initial payment ($%.2f).  Please contact the QBRC to resolve this.
            ''' % (qty, unit, current_charges_against_payment, payment_amount)
            return (False, rejection_reason)
        else: # the new charge did not exceed the payment, so it's allowed
            # update the budget to reflect this new charge and save it:
            budget.current_sum = new_sum
            budget.save()
            return (True, None)
    else:
        # if the payment_amount field is NULL, then this indicates something like an
        # open PO or some other payment that is not limited up front
        return (True, None)


def create_project_on_cnap(order_obj):
    '''
    This handles the actual work of contacting CNAP to generate a new project
    '''
    product = order_obj.product
    purchase = order_obj.purchase
    cnap_user = purchase.user
    client_email = cnap_user.user.email

    data = {}
    data['client_email'] = client_email
    data['workflow_pk'] = product.cnap_workflow_pk
    data['number_ordered'] = order.quantity

    headers = {'Authorization': 'Token %s' % settings.CNAP_TOKEN}
    
    r = requests.post(settings.CNAP_URL, data=data, headers=headers)

    if r.status_code != 200:
        message = '''
        The project creation call did not return 200.  The error was
        %s
        ''' % r.text
        handle_exception(None, message = message)
    


def fill_order(info_dict, payment_ref):
    '''
    Contacts CNAP to create a project

    At this point the payment, product choice, etc. 
    are all OK.  Just need to formally enter everything into the database
    '''

    pipeline = info_dict['PIPELINE']
    quantity_ordered = int(info_dict['NUM_OF_SAMPLE'])

    # go find the product corresponding to this pipeline:
    product = Product.objects.get(name=pipeline)

    # get the CnapUser instance
    base_user = get_user_model().objects.get(email=info_dict['EMAIL'])

    # get the research group:
    rg = ResearchGroup.objects.get(pi_email = info_dict['PI_EMAIL'] )

    cnap_user = CnapUser.objects.get(user=base_user, research_group=rg)

    # make a purchase:
    purchase = Purchase.objects.create(
        user = cnap_user
    )
    # create a new Order:
    order_obj = Order.objects.create(
        product = product,
        purchase = purchase,
        quantity = quantity_ordered,
        order_filled = False # until the project has successfully been created, leave F
    ) 

    # if this is a quantity-limited product, can now remove it from our inventory
    if product.is_quantity_limited:
        new_quantity = product.quantity - quantity_ordered
        product.quantity = new_quantity
        product.save()

    # contact CNAP to create the project
    create_project_on_cnap(order_obj)

    # if the prior function succeeded, then the order was filled
    order_obj.order_filled = True
    order_obj.save()

    # CNAP handles sending email to the requester.

def inform_user_of_invalid_order(info_dict, payment_ref, rejection_reason):
    '''
    Contact the client to let the know the request ws rejected.
    This is most often due to a budgeted amount being exceeded.
    '''
    # message the user
    subject = '[CNAP] Pipeline request rejected'

    plaintext_msg = '''
        The pipeline request you have submitted was not accepted for the following
        reason:
        --------------------------------------------
        %s
        --------------------------------------------

        The provided payment number was: %s

        Please work with the QBRC to resolve this matter.
 
        qBRC Team (qbrc@hsph.harvard.edu)

    ''' % (rejection_reason, info_dict['ACCT_NUM'])

    message_html = '''
        <html>
        <body>
        <p>The pipeline request you have submitted was not accepted for the following
        reason:</p>
        <hr>
        <p>%s</p>
        <hr>
        <p>The provided payment number was: %s</p>
        <p>qBRC Team <a href="mailto:qbrc@hsph.harvard.edu">qbrc@hsph.harvard.edu</a></p>
        </body>
        </html>
    ''' % (rejection_reason, info_dict['ACCT_NUM'])

    send_email(plaintext_msg, message_html, info_dict['EMAIL'], subject)


def ask_pipeline_requester_to_register_lab(info_dict):
    '''
    We use this function when a known user requests a pipeline
    but gives a PI we do not know of.  The PI is completely new to us,
    NOT a case where the user has to simply associate with that PI
    '''
    subject = '[CNAP] Please register your group first'

    plaintext_msg = '''
        The pipeline request you have submitted was not accepted since the PI
        you listed (%s) was not recognized.  If this was a simple typing error,
        please try again.  

        If the email you entered was correct, we first need to register
        this new principal investigator with our system.  

        qBRC Team (qbrc@hsph.harvard.edu)

    ''' % (info_dict['PI_EMAIL'])

    message_html = '''
        <html>
        <body>
        <p>The pipeline request you have submitted was not accepted since the PI
        you listed (%s) was not recognized.  If this was a simple typing error,
        please try again.  
        </p>
        <p>
        If the email you entered was correct, we first need to register
        this new principal investigator with our system. </p>
        <p>qBRC Team <a href="mailto:qbrc@hsph.harvard.edu">qbrc@hsph.harvard.edu</a></p>
        </body>
        </html>
    ''' % (info_dict['PI_EMAIL'])

    send_email(plaintext_msg, message_html, info_dict['EMAIL'], subject)

def handle_pipeline_request_email(info_dict):
    '''
    This is the starting point for business logic related to pipeline requests
    info_dict is a dictionary of the information parsed from the email
    '''

    # first check if we recognize their email.  If not, let them know they need to register
    try:
        base_user = get_user_model().objects.get(email = info_dict['EMAIL'])
    except get_user_model().DoesNotExist as ex:
        # let them know they have to register first
        ask_requester_to_register_first(info_dict['EMAIL'])
        return

    # if they are here, we at least know of their email.
    try:
        # check the PI email to see if their group is known to us.
        # it is possible they worked with a different lab previously
        # and have not associated their old email with their new lab
        rg = ResearchGroup.objects.get(pi_email=info_dict['PI_EMAIL'])
    except ResearchGroup.DoesNotExist:
        # so we know of the user, but not their PI
        # let them know they need to register with the new lab
        ask_pipeline_requester_to_register_lab(info_dict)
        return

    # if we make it here, they have correctly input their own email
    # and the email of a PI we know about.  They STILL might not be associated
    # with each other, so check that here
    try:
        cnap_user = CnapUser.objects.get(user=base_user, research_group=rg)
    except CnapUser.DoesNotExist:
        # let them know they have to register first
        ask_requester_to_associate_with_pi_first(info_dict)
        return

    # if we are here, then we know about the user and they have correctly associated with their known PI.
    # Check if they have an account string
    if info_dict['HAVE_ACCT_NUM'].lower()[0] == 'n':
        # send a message with cost info, etc.
        handle_no_payment_number(info_dict)

        # email QBRC indicating we have a request from a valid user/lab without acct string
        inform_qbrc_of_request_without_payment_number(info_dict)
        return

    # allegedly have an account number from a valid user at this point.  Check that the acct string
    # is indeed valid.
    try:
        payment_ref = Payment.objects.get(code=info_dict['ACCT_NUM'])
    except Payment.DoesNotExist:
        # the payment reference was not found.
        # message the user, ask them to try again(?)
        ask_user_to_resubmit_payment_info(info_dict)
        return

    # we now have a valid user + acct/payment.  We need to check that the payment is still
    # valid-- could have exhausted a budget, etc.
    is_valid_order, rejection_reason = check_that_purchase_is_valid_against_payment(info_dict, payment_ref)

    # if the purchase was ok, create the project on CNAP and inform the user
    if is_valid_order:
        fill_order(info_dict, payment_ref)
    else:
        # if the purchase was NOT ok (expired PO, budget consumed, etc.), let the user know
        inform_user_of_invalid_order(info_dict, payment_ref, rejection_reason)


def process_emails(mail, id_list, request_type):
    '''
    Actually grabs the emails from the server

    mail is an instance of imaplib.IMAP4_SSL
    id_list is a list of integers.  Each integer 
    is a UID of an email that matched our query.  It should be a list of 
    UIDs that we have not already checked.
    '''
    if len(id_list) == 0:
        return

    # go get the messages.  It is a list of where the odd indexes are byte strings (useless for our purposes here)
    # and the even-numbered indexes have tuples.
    messages = fetch_emails(mail, id_list)

    # As mentioned above, the even indexes have tuples.  The mail body itself is contained in the second
    # slot in the tuple
    for uid, message in zip(id_list, messages[::2]):
        try:
            mail_body = get_email_body(uid, message)

            if request_type == ACCOUNT_REQUEST:
                info_dict = parse_email_contents(mail_body, REQUIRED_ACCOUNT_CREATION_KEYS)
                handle_account_request_email(info_dict)
            elif request_type == PIPELINE_REQUEST:
                info_dict = parse_email_contents(mail_body, REQUIRED_PIPELINE_CREATION_KEYS)
                handle_pipeline_request_email(info_dict)

        except Exception as ex:
            # handle each email error individually.  This way a single
            # error does not block other requests that are correct.
            handle_exception(ex)


def query_imap_server_for_ids(mail, subject):
    '''
    Queries IMAP server for messages.  Returns a list of integers which
    are unique IDs.

    Queries by searching for a matching subject
    '''
    status, response = mail.search(None, subject)
    if status != 'OK':
        raise MailQueryException('The mailbox search did not succeed.')

    # response is something like: [b'749 753 754 755 784 785 786 787 788 789 790']
    # or [b'']

    # warn the admins- it is quite unlikely that there will be ZERO messages
    # matching our query.  Not strictly an error, but a warning
    if len(response[0]) == 0:
        #raise MailQueryWarning('Empty query response from IMAP server.')
        return []

    try:
        id_list = [int(x) for x in response[0].decode('utf-8').split(' ')]
        return id_list
    except Exception as ex:
        raise MailQueryException('Could not parse the response from imap server: %s' % response)


def get_account_creation_request_emails(mail):
    search_str = '(TO "qbrc@hsph.harvard.edu") (SUBJECT "[CNAP_Account]")'
    id_list = query_imap_server_for_ids(mail, search_str)
    return id_list


def get_pipeline_request_emails(mail):
    search_str = '(TO "qbrc@hsph.harvard.edu") (SUBJECT "[CNAP_Pipeline]")'
    id_list = query_imap_server_for_ids(mail, search_str)
    return id_list
    

def get_mailbox():
    '''
    Sets up the connection and returns a mailbox (an instance of imaplib.IMAP4_SSL)
    '''
    context = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
    try:
        mail = imaplib.IMAP4_SSL(settings.MAIL_HOST, settings.MAIL_PORT, ssl_context=context)
    except Exception as ex:
        print('could not reach')
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

    try:
        mail = get_mailbox()

        # work on the account request emails
        account_creation_id_list = get_account_creation_request_emails(mail)
        unprocessed_uids = [uid for uid in account_creation_id_list if is_new_email(settings.MAIL_HOST, settings.MAIL_FOLDER_NAME, uid)]
        process_emails(mail, unprocessed_uids, ACCOUNT_REQUEST)

        # work on the pipeline request emails
        pipeline_creation_id_list = get_pipeline_request_emails(mail)
        unprocessed_uids = [uid for uid in pipeline_creation_id_list if is_new_email(settings.MAIL_HOST, settings.MAIL_FOLDER_NAME, uid)]
        process_emails(mail, unprocessed_uids, PIPELINE_REQUEST)

    except Exception as ex:
        # This should catch any exceptions raised prior to the point at which we
        # start processing individual emails
        handle_exception(ex)
