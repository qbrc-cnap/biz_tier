import os
import json
import base64

from django.conf import settings
from django.contrib.auth import get_user_model

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.header import Header
from email.utils import formataddr

from googleapiclient import discovery
from google.oauth2.credentials import Credentials


def notify_admins(message, subject):
    admin_users = get_user_model().objects.filter(is_staff=True)
    for u in admin_users:
        send_email(message, message, u.email, subject)

def send_email(plaintext_msg, message_html, recipient, subject):

    # the message_html that was passed is everything *inside* the body tags
    # add the email signature, html + body tag

    html_template = '''
    <html>
    <body>
        %s

        <p>- qBRC Team</p>

        <div style="font-size: 12px; margin-top: 20px;">
        Quantitative Biomedical Research Center (qBRC)<br>
        Dept. of Biostatistics | Harvard T.H. Chan School of Public Health<br>
        655 Huntington Ave, 2-410 | Boston, MA 02115<br>
        <a href="mailto:qbrc@hsph.harvard.edu">qbrc@hsph.harvard.edu</a><br>
        <a href="https://www.hsph.harvard.edu/qbrc">https://www.hsph.harvard.edu/qbrc</a>   
        </div>
    </body>
    </html>
    '''

    plaintext_template = '''
        %s
        
        -qBRC Team

        Quantitative Biomedical Research Center (qBRC)
        Dept. of Biostatistics | Harvard T.H. Chan School of Public Health
        655 Huntington Ave, 2-410 | Boston, MA 02115
        Email: qbrc@hsph.harvard.edu
        https://www.hsph.harvard.edu/qbrc 
    '''

    full_html = html_template % message_html
    full_plaintext = plaintext_template % plaintext_msg

    if recipient in settings.TEST_EMAIL_ADDRESSES:
        print('Sending mock email to %s' % recipient)
    else:
        j = json.load(open(settings.EMAIL_CREDENTIALS_FILE))
        credentials = Credentials(j['token'],
                      refresh_token=j['refresh_token'], 
                      token_uri=j['token_uri'], 
                      client_id=j['client_id'], 
                      client_secret=j['client_secret'], 
                      scopes=j['scopes'])

        service = discovery.build('gmail', 'v1', credentials = credentials)

        sender = 'qbrc@g.harvard.edu'
        message = MIMEMultipart('alternative')

        # create the plaintext portion
        part1 = MIMEText(full_plaintext, 'plain')

        # create the html:
        part2 = MIMEText(full_html, 'html')

        message.attach(part1)
        message.attach(part2)

        message['To'] = recipient
        message['From'] = formataddr((str(Header('QBRC', 'utf-8')), sender))
        message['subject'] = subject
        msg = {'raw': base64.urlsafe_b64encode(message.as_string().encode()).decode()}
        sent_message = service.users().messages().send(userId='me', body=msg).execute()
