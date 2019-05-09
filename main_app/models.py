from django.db import models
from django.contrib.auth.models import AbstractUser
from django.contrib.auth.base_user import BaseUserManager

from django.contrib.auth import get_user_model

class CustomUserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra_fields):
        """
        Create and save a user with the given email, and password.
        """
        if not email:
            raise ValueError('Email must be set')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(email, password=password, **extra_fields)

class BaseUser(AbstractUser):
    '''
    Declaring this here allows us the flexibility to add additional
    behavior at a later time.
    '''
    username = None
    email = models.EmailField(unique=True, null=False, max_length=255)
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []
    objects = CustomUserManager()


    def __str__(self):
        return '%s, %s (%s)' % (self.last_name, self.first_name, self.email)


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

    # does the PI have a Harvard appointment?
    has_harvard_appointment = models.BooleanField(default=False)

    # the department (e.g. Biostatistics).  Can be null since not always applicable
    department = models.CharField(max_length=200, null=True)

    # mailing address, etc.:
    address_lines = models.CharField(max_length=200, null=True, blank=True)
    city = models.CharField(max_length=50, null=True, blank=True)
    state = models.CharField(max_length=20, null=True, blank=True)
    postal_code = models.CharField(max_length=10, null=True, blank=True)
    country = models.CharField(max_length=100, null=True, blank=True)


class FinancialCoordinator(models.Model):
    '''
    This keeps track of information about a ResearchGroup's finance coordinator
    '''
    contact_name = models.CharField(max_length=100, null=True, blank=True)
    contact_email = models.EmailField(max_length=100, null=True, blank=True)
    research_group = models.ForeignKey(ResearchGroup, on_delete=models.CASCADE)


class Payment(models.Model):
    '''
    This class tracks how a group pays for analyses.  A PI can open a PO and have multiple
    purchases (by potentially multiple users) can be made against that PO.  
    '''
    CREDIT_CARD = 'CC'
    PURCHASE_ORDER = 'PO'
    COSTING_STRING = 'CS'

    # for using choices, need to define a tuple of tuples
    # the first item in the nested tuple is the value that is stored in the db,
    # while the second is a human-readable name
    PAYMENT_TYPES = (
        (CREDIT_CARD, 'Credit card'),
        (PURCHASE_ORDER, 'Purchase order (PO)'),
        (COSTING_STRING, 'Costing string')
    )
    payment_type = models.CharField(max_length = 2, choices=PAYMENT_TYPES)

    # the payment number (e.g. PO#, masked credit no.)
    number = models.CharField(max_length=200, null=False, blank=False)

    # when was the payment made:
    payment_date = models.DateTimeField(null=True)

    # expiration date for the payment
    payment_expiration_date = models.DateField(null=True)

    # to which research group is this payment applied:
    client = models.ForeignKey(ResearchGroup, on_delete=models.CASCADE)

    # for each payment we create a code such that lab members can reference that code
    # during checkout and that will associate their purchase this payment
    code = models.CharField(max_length=20, blank=True, null=True)

    # the amount of the payment:
    # allow null for an open PO, or similar
    payment_amount = models.FloatField(null=True)


class Budget(models.Model):
    '''
    This allows us to check if purchases made against a payment are valid, or whether they have exceeded.
    We keep this separate from the Payment table since that payments should not care about the concept of a budget
    '''

    # the payment we are referencing
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE)

    # current_usage.  This is updated as purchases are made against the payment
    current_sum = models.FloatField(default=0.0)

    
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
    purchase_number = models.CharField(max_length=200, blank=True, null=True)

    issue_date = models.DateField(null=True, blank=True)
    close_date = models.DateField(null=True, blank=True)


class Product(models.Model):
    '''
    This class captures the notion of a product that will be sold
    '''

    # a unique product ID is implied with the primary key

    # a name for the product:
    name = models.CharField(max_length=1000, unique=True, blank=False, null=False)

    # a verbose description, allowed to be empty:
    description = models.CharField(max_length=5000, blank=True, null=True)

    # how many of this product are available.  Sort of an abstract concept for 
    # software services, but in the instance wheere we create a product for a specific 
    # group and they pay for 100 units, this can enforce that they cannot purchase more 
    # than that amount
    quantity = models.PositiveIntegerField(null=True)

    # a boolean to track whether the product is effectively unlimited in
    # terms of stock
    # If True, then a limit is imposed and need to check the quantity field
    # By default, it is False, which creates unlimited quantity of a product
    # For lab-specific products, we can limit the quantity
    is_quantity_limited = models.BooleanField(default=False)

    # the primary key of the workflow from the actual CNAP application.  This
    # allows us to automatically generate projects based on the particular workflow
    cnap_workflow_pk = models.PositiveIntegerField(null=False)

    # how much does each unit of this product/analysis cost?  Allows us to check budgets.
    unit_cost = models.FloatField(null=False)


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