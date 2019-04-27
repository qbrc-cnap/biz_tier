from django.db import models
from django.contrib.auth.models import AbstractUser
from django.contrib.auth import get_user_model


class BaseUser(AbstractUser):
    '''
    Declaring this here allows us the flexibility to add additional
    behavior at a later time.
    '''
    pass


class PendingUser(models.Model):
    '''
    This class is not a subtype of any Django user, but rather holds
    information about potential users until an administrator and PI can verify the request.
    '''

    # was this requested by a principal investigator
    is_pi = models.BooleanField(default = False, null=False)

    # a JSON-format string holding the info we parsed from the email.
    # Since PIs and non-PIs have different info, this keeps us from having
    # to track different types of pending users.  Once the pending user is
    # approved, we can parse this string and create users of the appropriate types
    info_json = models.CharField(max_length=10000, null=False, blank=False)

    # a long hash invitation key.  Prior to the QBRC approving an account, this is set
    # to null.  Once approved by the QBRC, a key will be generated and filled-in.
    approval_key = models.CharField(max_length=100, null=True, blank=True)

    # the date of the request so we may expire those that are old
    request_date = models.DateField(auto_now_add = True)


class ProcessedEmail(models.Model):
    '''
    We query the IMAP server to get emails with a particular subject.  Since these emails go to our inboxes, we cannot 
    use the 'READ' flag to know whether this application has seen/processed the email before.  Hence, we have to track 
    the UIDs that we DO parse/handle so we don't end up repeating work.
    ''' 

    # in case we use other mail servers, need to track the UID along with the mail server
    mail_server_name = models.CharField(max_length=500, null=False, blank=False)

    # also need to track the folder.  UID can change if folder changes
    mail_folder_name = models.CharField(max_length=100, null=False, blank=False)

    # the message UID.  Supposed to be a non-zero integer.  
    message_uid = models.PositiveIntegerField(null=False, blank=False)


class Organization(models.Model):
    '''
    This class adds an institutional hierarchy.  In this way, multiple research
    groups of individuals can be grouped according to this class
    '''
    name = models.CharField(max_length=200, blank=True, null=True)

    # other info about an organization?


class ResearchGroup(models.Model):
    '''
    This allows us to aggregate multiple users under a single "lab" or group

    For individuals, they are their own research group.  Their PI is themself.
    '''
    
    # the name of the PI.  Since a PI may never be an actual user of the 
    # application, we do not keep the PI as a User object themself.
    pi_name = models.CharField(max_length=200, blank=False, null=False)

    pi_email = models.EmailField(unique=True, null=False, max_length=255)

    # We allow the organization to be null
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, null=True)

    


class Payment(models.Model):
    '''
    This class tracks how a group pays for analyses.  A PI can open a PO and have multiple
    purchases (by potentially multiple users) can be made against that PO.  
    '''
    CREDIT_CARD = 'CC'
    PURCHASE_ORDER = 'PO'
    JOURNAL_NUMBER = 'JN'

    # for using choices, need to define a tuple of tuples
    # the first item in the nested tuple is the value that is stored in the db,
    # while the second is a human-readable name
    PAYMENT_TYPES = (
        (CREDIT_CARD, 'Credit card'),
        (PURCHASE_ORDER, 'Purchase order (PO)'),
        (JOURNAL_NUMBER, 'Journal number')
    )
    payment_type = models.CharField(max_length = 2, choices=PAYMENT_TYPES)

    # the payment number (e.g. PO#, masked credit no.)
    number = models.CharField(max_length=200, null=False, blank=False)

    # when was the payment made:
    payment_date = models.DateTimeField(null=True)

    # to which research group is this payment applied:
    client = models.ForeignKey(ResearchGroup, on_delete=models.CASCADE)

    # for each payment we create a code such that lab members can reference that code
    # during checkout and that will associate their purchase this payment
    code = models.CharField(max_length=20, blank=True, null=True)


class CnapUser(models.Model):
    '''
    This adds to the base class of User.  The reason is that we have users of
    *this* application (e.g. our admins), but there are users of the CNAP application
    who we need to track and group
    '''

    # a reference to the base user, which has the basic info about this user    
    user = models.ForeignKey(get_user_model(), on_delete=models.CASCADE)

    # a user can be associated with potentially multiple research groups, and obviously
    # each research group has multiple users, so we establish a many-to-many relationship
    research_group = models.ManyToManyField(ResearchGroup)

    # when they joined
    join_date = models.DateField(auto_now_add = True)


class Purchase(models.Model):
    '''
    A purchase represents the collection of things bought by a user
    '''
    user = models.ForeignKey(CnapUser, on_delete=models.CASCADE)

    # a purchase ID which we can link to the store
    purchase_number = models.CharField(max_length=200, blank=False, null=False)

    issue_date = models.DateField(null=True, blank=True)
    close_date = models.DateField(null=True, blank=True)


class Product(models.Model):
    '''
    This class captures the notion of a product that will be sold
    '''

    # a unique product ID is implied with the primary key

    # a name for the product:
    name = models.CharField(max_length=1000, blank=False, null=False)

    # a verbose description, allowed to be empty:
    description = models.CharField(max_length=5000, blank=True, null=True)

    # how many of this product are available.  Sort of an abstract concept for 
    # software services, but in the instance wheere we create a product for a specific 
    # group and they pay for 100 units, this can enforce that they cannot purchase more 
    # than that amount
    quantity = models.PositiveIntegerField(null=True)

    # a boolean to track whether the product is effectively unlimited
    # If True, then a limit is imposed and need to check the quantity field
    # By default, it is False, which creates unlimited quantity of a product
    is_quantity_limited = models.BooleanField(default=False)


class Order(models.Model):
    '''
    This class captures the notion of an order, which represents a product that
    one wishes to purchase.  Multiple orders are grouped together at the Purchase Level
    '''

    # the product that was purchased
    product = models.ForeignKey(Product, on_delete=models.CASCADE)

    # the purchase this order belongs to:
    purchase = models.ForeignKey(Purchase, on_delete=models.CASCADE)

    # how many of the above product were ordered?
    quantity = models.PositiveIntegerField(null=False)

    # This bool tracks whether the order has been filled.  e.g. we can hold 
    # an order until some other condition is met.  Perhaps the purchase was made with a
    # PO that has since been exhausted
    order_filled = models.BooleanField(default=False)