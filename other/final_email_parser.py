from email.parser import BytesParser
from email.policy import default
from bs4 import BeautifulSoup
import re

def get_order_id(soup):
    '''
    Extracts the order ID and returns a string
    '''
    table = soup.find_all(id='tempOrderNumberStore')
    table=table[0]
    all_td = table.find_all('td')
    t0 = all_td[0]
    x = t0.find_all('span', 'data')[0]
    order_id = x.text.strip() # a string
    return order_id


def parse_order_row(tr_element):
    '''
    Parses the row of a product table.  Returns a dict of the info
    '''
    all_td = tr_element.find_all('td')
    values = []
    for tt in all_td:
        values.append(tt.text.strip())
    return dict(zip(['product_name','product_id','quantity','unit_price', 'total_order_price'], values))


def get_purchase_details(soup):
    '''
    Gets all the purchase details.  Returns a list of dicts.  Each item
    has the info about a single order
    '''
    table =soup.find_all(id='tempItemDetailsProduct')
    table = table[0]
    all_tr = table.find_all('tr')
    at_subtotal = False
    index = 1 # start at 1 since index 0 refers to the header row, which we do not need
    purchase_list = []
    while not at_subtotal:
        tr = all_tr[index]
        #print(tr)
        try:
            css_classes = tr['class']
        except KeyError:
            css_classes = []
        if 'subtotal' in css_classes:
            at_subtotal = True
        else:
            product_dict = parse_order_row(tr)
            #TODO: do something with this
            purchase_list.append(product_dict)
        index += 1
    return purchase_list

def get_client_email(soup):
    '''
    Returns the email address of the client who ordered the analysis
    '''
    billing_tables = soup.find_all(id='tempBilling')
    user_emails = []
    for t in billing_tables:
        email_anchors = t.find_all('a', href=re.compile('mailto'))
        if email_anchors:
            for a in email_anchors:
                email_address = a.text.strip()
                user_emails.append(email_address)
    if user_emails:
        if len(user_emails) > 1:
            print('Multiple emails encountered')
        return user_emails[0]


def get_additional_q_and_a(soup):
    '''
    Returns information from the additional questions we ask during the purchase.
    Needs to stay up to date with the questions we ask
    '''
    footer = t = soup.find_all(id='templateFooter')[0]
    tds = footer.find_all('td')
    if len(tds) == 1:
        td = tds[0]
        questions = [x.text.strip() for x in td.select('.question')]
        answers = [x.text.strip() for x in td.select('.answer')]
        return dict(zip(questions, answers))
    else:
        return {} 


if __name__ == '__main__':

    with open('scratch/example_email.txt', 'rb') as fp:
        whole_email = BytesParser(policy=default).parse(fp)

    body = whole_email.get_body()

    if body['content-type'].subtype == 'html':
        html_str = body.get_content()

    soup = BeautifulSoup(html_str, 'html.parser')

    order_id = get_order_id(soup)

    purchase = get_purchase_details(soup)

    client_email = get_client_email(soup)

    additional_q_and_a = get_additional_q_and_a(soup)

    # print outs for testing purposes:
    print('Order: %s' % order_id)
    print('Client: %s' % client_email)
    print('-'*50)
    for p in purchase:
        print(p)
        print('*'*30)
    for q,a in additional_q_and_a.items():
        print('%s: %s' % (q,a))
    