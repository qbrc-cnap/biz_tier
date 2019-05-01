import json

import unittest.mock as mock

from django.test import TestCase
from django.conf import settings
from django.contrib.auth import get_user_model

from main_app.tasks import MailQueryException, \
    get_mailbox, \
    check_for_qualtrics_survey_results, \
    query_imap_server_for_ids, \
    parse_email_contents, \
    MailParseException, \
    handle_account_request_email, \
    staff_approve_pending_user, \
    process_emails, \
    pi_approve_pending_user, \
    ACCOUNT_REQUEST

from main_app.models import BaseUser, \
    ResearchGroup, \
    Organization, \
    CnapUser, \
    PendingUser, \
    FinancialCoordinator

class EmailBodyParser(TestCase):
    def setUp(self):
        pass
    
    def tearDown(self):
        pass


    def test_missing_key_generates_error(self):
        '''
        Tests the case where the email body is missing one of the
        required keys
        '''
        required_keyset = ['FOO', 'BAR', 'BAZ']
        payload = '''
        <html>
        <body>
        FOO:Paired End RNASeq Analysis <br>
        BAR:Illumina Paired End 75bp <br>
        </body></html>
        '''
        with self.assertRaises(MailParseException):
            parse_email_contents(payload, required_keyset)

    def test_parser_returns_expected_object(self):
        '''
        Tests that we get a dictionary as expected, leaving
        out any extra content
        '''
        required_keyset = ['FOO', 'BAR']
        payload = '''
        <html>
        <body>
        FOO:Paired End RNASeq Analysis <br>
        BAR:Illumina Paired End 75bp <br>
        BAZ:Something extra <br>
        </body></html>
        '''
        d = parse_email_contents(payload, required_keyset)
        expected_d = {
            'FOO':'Paired End RNASeq Analysis', 
            'BAR': 'Illumina Paired End 75bp'
        }
        self.assertEqual(d, expected_d)

    def test_empty_survey_response_is_ok(self):
        '''
        Some of the survey results can be emailed as empty, e.g. the "BAR"
        key below
        '''
        required_keyset = ['FOO', 'BAR']
        payload = '''
        <html>
        <body>
        FOO:Paired End RNASeq Analysis <br>
        BAR:<br>
        BAZ:Something extra <br>
        </body></html>
        '''
        d = parse_email_contents(payload, required_keyset)
        expected_d = {
            'FOO':'Paired End RNASeq Analysis', 
            'BAR': ''
        }
        self.assertEqual(d, expected_d)


class AccountRequestTestCase(TestCase):
    '''
    Tests the functionality/logic of the account request workflow
    '''
    def setUp(self):

        # this would be the info parsed from a PI who
        # requests an account for themself
        # it is ok that the financial info is 'blank'
        self.pi_info_dict = {
            'FIRST_NAME': 'John',
            'LAST_NAME': 'Smith',
            'EMAIL': settings.TEST_PI_EMAIL,
            'PHONE': '123-456-7890',
            'PI': 'Yes',
            'PI_FIRST_NAME': 'John',
            'PI_LAST_NAME': 'Smith',
            'PI_EMAIL': settings.TEST_PI_EMAIL,
            'PI_PHONE': '123-456-7890',
            'HARVARD_APPOINTMENT': 'Yes',
            'ORGANIZATION': 'HSPH',
            'DEPARTMENT': 'Biostatistics',
            'FINANCIAL_CONTACT': '',
            'FINANCIAL_EMAIL': '',
            'ADDRESS': '',
            'CITY': '',
            'STATE': '',
            'POSTAL_CODE': '',
            'COUNTRY': ''
        }

        # this is used for test case where
        # labs are switched
        self.old_pi_info_dict = {
            'FIRST_NAME': 'Alice',
            'LAST_NAME': 'Smith',
            'EMAIL': settings.TEST_ANOTHER_PI_EMAIL,
            'PHONE': '123-456-7890',
            'PI': 'Yes',
            'PI_FIRST_NAME': 'Alice',
            'PI_LAST_NAME': 'Smith',
            'PI_EMAIL': settings.TEST_ANOTHER_PI_EMAIL,
            'PI_PHONE': '123-456-7890',
            'HARVARD_APPOINTMENT': 'Yes',
            'ORGANIZATION': 'HSPH',
            'DEPARTMENT': 'Biostatistics',
            'FINANCIAL_CONTACT': '',
            'FINANCIAL_EMAIL': '',
            'ADDRESS': '',
            'CITY': '',
            'STATE': '',
            'POSTAL_CODE': '',
            'COUNTRY': ''
        }

        # this would be the info parsed from a regular
        # user who is not a PI
        # it is ok that the financial info is 'blank'
        self.postdoc_info_dict = {
            'FIRST_NAME': 'Jane',
            'LAST_NAME': 'Postdoc',
            'EMAIL': settings.TEST_POSTDOC_EMAIL,
            'PHONE': '123-456-7890',
            'PI': 'No',
            'PI_FIRST_NAME': 'John',
            'PI_LAST_NAME': 'Smith',
            'PI_EMAIL': settings.TEST_PI_EMAIL,
            'PI_PHONE': '123-456-7890',
            'HARVARD_APPOINTMENT': 'Yes',
            'ORGANIZATION': 'HSPH',
            'DEPARTMENT': 'Biostatistics',
            'FINANCIAL_CONTACT': '',
            'FINANCIAL_EMAIL': '',
            'ADDRESS': '',
            'CITY': '',
            'STATE': '',
            'POSTAL_CODE': '',
            'COUNTRY': ''
        }

        # this would be the info parsed from a regular
        # user who is not a PI (a grad student)
        # it is ok that the financial info is 'blank'
        self.gradstudent_info_dict = {
            'FIRST_NAME': 'Jim',
            'LAST_NAME': 'Grad',
            'EMAIL': settings.TEST_GRAD_STUDENT_EMAIL,
            'PHONE': '123-456-7890',
            'PI': 'No',
            'PI_FIRST_NAME': 'John',
            'PI_LAST_NAME': 'Smith',
            'PI_EMAIL': settings.TEST_PI_EMAIL,
            'PI_PHONE': '123-456-7890',
            'HARVARD_APPOINTMENT': 'Yes',
            'ORGANIZATION': 'HSPH',
            'DEPARTMENT': 'Biostatistics',
            'FINANCIAL_CONTACT': '',
            'FINANCIAL_EMAIL': '',
            'ADDRESS': '',
            'CITY': '',
            'STATE': '',
            'POSTAL_CODE': '',
            'COUNTRY': ''
        }

    def tearDown(self):
        pass


    @mock.patch('main_app.tasks.inform_user_of_existing_account')
    def test_repeated_account_request_by_pi(self, mock_inform_user_of_existing_account):
        '''
        This covers the case where a PI (who already has a ResearchGroup)
        makes another request for an account.  Test that we just message them
        since there is nothing to do (they already have an acct)
        '''
        # create a user who is a PI:
        pi_user = BaseUser.objects.create(
            first_name = 'John',
            last_name = 'Doe',
            email = settings.TEST_PI_EMAIL
        )

        # create their research group:
        org = Organization.objects.create(name=self.pi_info_dict['ORGANIZATION'])
        rg = ResearchGroup.objects.create(
            organization = org,
            pi_email = self.pi_info_dict['PI_EMAIL'],
            pi_name = '%s %s' % (self.pi_info_dict['PI_FIRST_NAME'], self.pi_info_dict['PI_LAST_NAME']),
            has_harvard_appointment = True if self.pi_info_dict['HARVARD_APPOINTMENT'].lower() == 'y' else False,
            department = self.pi_info_dict['DEPARTMENT'],
            address_lines = self.pi_info_dict['ADDRESS'],
            city = self.pi_info_dict['CITY'],
            state = self.pi_info_dict['STATE'],
            postal_code = self.pi_info_dict['POSTAL_CODE'],
            country = self.pi_info_dict['COUNTRY']
        )

        handle_account_request_email(self.pi_info_dict)
        mock_inform_user_of_existing_account.assert_called_once()

    @mock.patch('main_app.tasks.handle_account_request_for_existing_user')
    def test_existing_regular_user_goes_to_correct_handler(self, mock_handle_account_request_for_existing_user):
        '''
        Simply tests that we hit the right 'main' method for the case
        where we have an existing user
        '''
        # create a regular user:
        regular_user = BaseUser.objects.create(
            first_name = 'Jane',
            last_name = 'Postdoc',
            email = settings.TEST_POSTDOC_EMAIL
        )
        handle_account_request_email(self.postdoc_info_dict)
        mock_handle_account_request_for_existing_user.assert_called_once()


    @mock.patch('main_app.tasks.handle_account_request_for_new_user')
    def test_new_regular_user_goes_to_correct_handler(self, mock_handle_account_request_for_new_user):
        '''
        Simply tests that we hit the right 'main' method for the case
        where we have a new regular user
        '''

        # here the postdoc user has not been created yet, so they are new
        handle_account_request_email(self.postdoc_info_dict)
        mock_handle_account_request_for_new_user.assert_called_once()
        
    @mock.patch('main_app.tasks.handle_account_request_for_new_user')
    def test_new_pi_goes_to_correct_handler(self, mock_handle_account_request_for_new_user):
        '''
        Simply tests that we hit the right 'main' method for the case
        where we have a new PI
        '''
        handle_account_request_email(self.pi_info_dict)
        mock_handle_account_request_for_new_user.assert_called_once()

    @mock.patch('main_app.tasks.handle_unknown_pi_account')
    def test_existing_user_with_unknown_pi_goes_to_correct_method(self, mock_handle_unknown_pi_account):
        '''
        If we have an existing user, but there is no research group.  This might be the 
        case if we had a user who was previously with one lab.  They then change to a 
        new lab where the PI has NOT previously worked with us.  Thus, the postdoc is known
        to us, but their PI does NOT have an account

        Check that we call the handle_unknown_pi_account function

        (case 7)
        '''
        # create a regular user:
        regular_user = BaseUser.objects.create(
            first_name = 'Jane',
            last_name = 'Postdoc',
            email = settings.TEST_POSTDOC_EMAIL
        )
        handle_account_request_email(self.postdoc_info_dict)
        mock_handle_unknown_pi_account.assert_called_once()

    @mock.patch('main_app.tasks.inform_user_of_existing_account')
    def test_existing_user_requesting_account_for_previously_associated_group_only_sends_email(self, mock_inform_user_of_existing_account):
        '''
        This tests the case where a regular user effectively makes a duplicate request.

        Just send them a message saying they are already registered

        (case 5)
        '''

        # create a user who is a PI:
        pi_user = BaseUser.objects.create(
            first_name = 'John',
            last_name = 'Doe',
            email = settings.TEST_PI_EMAIL
        )

        # create a regular user:
        regular_user = BaseUser.objects.create(
            first_name = 'Jane',
            last_name = 'Postdoc',
            email = settings.TEST_POSTDOC_EMAIL
        )

        # create their research group:
        org = Organization.objects.create(name=self.pi_info_dict['ORGANIZATION'])
        rg = ResearchGroup.objects.create(
            organization = org,
            pi_email = self.pi_info_dict['PI_EMAIL'],
            pi_name = '%s %s' % (self.pi_info_dict['PI_FIRST_NAME'], self.pi_info_dict['PI_LAST_NAME']),
            has_harvard_appointment = True if self.pi_info_dict['HARVARD_APPOINTMENT'].lower() == 'y' else False,
            department = self.pi_info_dict['DEPARTMENT'],
            address_lines = self.pi_info_dict['ADDRESS'],
            city = self.pi_info_dict['CITY'],
            state = self.pi_info_dict['STATE'],
            postal_code = self.pi_info_dict['POSTAL_CODE'],
            country = self.pi_info_dict['COUNTRY']
        )

        # associate those users with the research group:
        u1 = CnapUser.objects.create(user=pi_user)
        u1.research_group.add(rg)
        u1.save()
        u2 = CnapUser.objects.create(user=regular_user)
        u2.research_group.add(rg)
        u2.save()

        handle_account_request_email(self.postdoc_info_dict)
        mock_inform_user_of_existing_account.assert_called_once()

    @mock.patch('main_app.tasks.send_approval_email_to_pi')
    def test_existing_user_associating_with_lab_new_to_them(self, mock_send_approval_email_to_pi):
        '''
        This tests the case where a postdoc may switch labs.  We know about them from a 
        previous lab, but they switch to another lab that we work with.  Thus, we have 
        records of both the user and the lab, but they are NOT associated yet.

        Test that a PendingUser object is created and the PI of the new lab is
        informed for confirmation.

        (case 4)
        '''

        # create a user who is a PI (the PI of the lab this
        # person is trying to join)
        pi_user = BaseUser.objects.create(
            first_name = 'John',
            last_name = 'Smith',
            email = settings.TEST_PI_EMAIL
        )

        # create a user who is a PI (the PI of OLD lab
        # for the regular user)
        old_pi_user = BaseUser.objects.create(
            first_name = 'Alice',
            last_name = 'Smith',
            email = settings.TEST_ANOTHER_PI_EMAIL
        )

        # create a regular user.  This user
        # was previously associated with another lab
        regular_user = BaseUser.objects.create(
            first_name = 'Jane',
            last_name = 'Postdoc',
            email = settings.TEST_POSTDOC_EMAIL
        )

        # create a research group for the old group they were
        # associated with:
        old_org = Organization.objects.create(name=self.old_pi_info_dict['ORGANIZATION'])
        old_rg = ResearchGroup.objects.create(
            organization = old_org,
            pi_email = self.old_pi_info_dict['PI_EMAIL'],
            pi_name = '%s %s' % (self.old_pi_info_dict['PI_FIRST_NAME'], self.old_pi_info_dict['PI_LAST_NAME']),
            has_harvard_appointment = True if self.old_pi_info_dict['HARVARD_APPOINTMENT'].lower() == 'y' else False,
            department = self.old_pi_info_dict['DEPARTMENT'],
            address_lines = self.old_pi_info_dict['ADDRESS'],
            city = self.old_pi_info_dict['CITY'],
            state = self.old_pi_info_dict['STATE'],
            postal_code = self.old_pi_info_dict['POSTAL_CODE'],
            country = self.old_pi_info_dict['COUNTRY']
        )

        # create a research group for the new group they are joining:
        org = Organization.objects.create(name=self.pi_info_dict['ORGANIZATION'])
        rg = ResearchGroup.objects.create(
            organization = org,
            pi_email = self.pi_info_dict['PI_EMAIL'],
            pi_name = '%s %s' % (self.pi_info_dict['PI_FIRST_NAME'], self.pi_info_dict['PI_LAST_NAME']),
            has_harvard_appointment = True if self.pi_info_dict['HARVARD_APPOINTMENT'].lower() == 'y' else False,
            department = self.pi_info_dict['DEPARTMENT'],
            address_lines = self.pi_info_dict['ADDRESS'],
            city = self.pi_info_dict['CITY'],
            state = self.pi_info_dict['STATE'],
            postal_code = self.pi_info_dict['POSTAL_CODE'],
            country = self.pi_info_dict['COUNTRY']
        )

        # associate the PI users with their research groups:
        u1 = CnapUser.objects.create(user=pi_user)
        u1.research_group.add(rg)
        u1.save()

        u2 = CnapUser.objects.create(user=old_pi_user)
        u2.research_group.add(old_rg)
        u2.save()

        # associate the regular user with their old lab:
        u3 = CnapUser.objects.create(user=regular_user)
        u3.research_group.add(old_rg)
        u3.save()

        # now ready to check the logic.  Need to see that the new 
        # PI is contacted
        handle_account_request_email(self.postdoc_info_dict)
        mock_send_approval_email_to_pi.assert_called_once()
        p = PendingUser.objects.all()
        self.assertEqual(len(p), 1)

    @mock.patch('main_app.tasks.inform_staff_of_new_account')
    def test_new_user_with_new_pi_starts_expected_process(self, mock_inform_staff_of_new_account):
        '''
        Here we have a new user and a new PI (i.e. regular user
        is making the request, NOT the PI).
        Test that we create a PendingUser and inform the QBRC staff

        (Case 1)
        '''
        p = PendingUser.objects.all()
        self.assertEqual(len(p), 0)
        handle_account_request_email(self.postdoc_info_dict)
        p = PendingUser.objects.all()
        self.assertEqual(len(p), 1)
        mock_inform_staff_of_new_account.assert_called_once()

    @mock.patch('main_app.tasks.send_approval_email_to_pi')
    @mock.patch('main_app.tasks.send_account_pending_email_to_requester')
    def test_new_user_associating_new_pi(self, 
        mock_send_account_pending_email_to_requester, 
        mock_send_approval_email_to_pi):
        '''
        Here we have a new user attempting to associate with an existing lab.
        Test that the PendingUser instance is created, the pi is emailed for
        authorization, and the user is sent an email

        (case 2)
        '''
        # create a user who is a PI:
        pi_user = BaseUser.objects.create(
            first_name = 'John',
            last_name = 'Doe',
            email = settings.TEST_PI_EMAIL
        )

        # create their research group:
        org = Organization.objects.create(name=self.pi_info_dict['ORGANIZATION'])
        rg = ResearchGroup.objects.create(
            organization = org,
            pi_email = self.pi_info_dict['PI_EMAIL'],
            pi_name = '%s %s' % (self.pi_info_dict['PI_FIRST_NAME'], self.pi_info_dict['PI_LAST_NAME']),
            has_harvard_appointment = True if self.pi_info_dict['HARVARD_APPOINTMENT'].lower() == 'y' else False,
            department = self.pi_info_dict['DEPARTMENT'],
            address_lines = self.pi_info_dict['ADDRESS'],
            city = self.pi_info_dict['CITY'],
            state = self.pi_info_dict['STATE'],
            postal_code = self.pi_info_dict['POSTAL_CODE'],
            country = self.pi_info_dict['COUNTRY']
        )

        # associate those PI with their research group:
        u1 = CnapUser.objects.create(user=pi_user)
        u1.research_group.add(rg)
        u1.save()

        # at this point a lab has been created.  Account request
        # is received from a new user
        handle_account_request_email(self.postdoc_info_dict)
        mock_send_account_pending_email_to_requester.assert_called_once()
        mock_send_approval_email_to_pi.assert_called_once()
        p = PendingUser.objects.all()
        self.assertEqual(len(p), 1)


    @mock.patch('main_app.tasks.inform_staff_of_new_account')
    @mock.patch('main_app.tasks.send_self_approval_email_to_pi')
    def test_staff_approval_for_pi_self_request(self, 
        mock_send_self_approval_email_to_pi,
        mock_inform_staff_of_new_account):
        '''
        Here we test that the QBRC has approved a request submitted
        by a PI for themself.

        Test that the PI is sent a confirmation email that they will
        click to finalize their account

        (part of case 3)
        '''
        # check that we do not have any PendingUser to start:
        p = PendingUser.objects.all()
        self.assertEqual(len(p), 0)

        # Account request received from PI for themself:
        handle_account_request_email(self.pi_info_dict)

        # that action above should create a PendingUser
        # and sent email to QBRC
        p = PendingUser.objects.all()
        self.assertEqual(len(p), 1)
        mock_inform_staff_of_new_account.assert_called_once()

        # now we mock the QBRC approving this PI's account:
        pk = p[0].pk
        staff_approve_pending_user(pk)
        mock_send_self_approval_email_to_pi.assert_called_once()

    @mock.patch('main_app.tasks.send_approval_email_to_pi')
    @mock.patch('main_app.tasks.send_account_pending_email_to_requester')
    def test_staff_approval_for_regular_user_request(self, 
        mock_send_account_pending_email_to_requester, 
        mock_send_approval_email_to_pi
        ):
        '''
        Here we test that the activity once the QBRC has approved a request submitted
        by a regular user for a given lab

        Test that the PI is sent a confirmation email and the regular 
        user gets an info email.

        Also check that we do not (yet!) create any ResearchGroup and new user
        instances
        '''
        # create a user who is a PI:
        pi_user = BaseUser.objects.create(
            first_name = 'John',
            last_name = 'Doe',
            email = settings.TEST_PI_EMAIL
        )

        # create their research group:
        org = Organization.objects.create(name=self.pi_info_dict['ORGANIZATION'])
        rg = ResearchGroup.objects.create(
            organization = org,
            pi_email = self.pi_info_dict['PI_EMAIL'],
            pi_name = '%s %s' % (self.pi_info_dict['PI_FIRST_NAME'], self.pi_info_dict['PI_LAST_NAME']),
            has_harvard_appointment = True if self.pi_info_dict['HARVARD_APPOINTMENT'].lower() == 'y' else False,
            department = self.pi_info_dict['DEPARTMENT'],
            address_lines = self.pi_info_dict['ADDRESS'],
            city = self.pi_info_dict['CITY'],
            state = self.pi_info_dict['STATE'],
            postal_code = self.pi_info_dict['POSTAL_CODE'],
            country = self.pi_info_dict['COUNTRY']
        )

        # associate those PI with their research group:
        u1 = CnapUser.objects.create(user=pi_user)
        u1.research_group.add(rg)
        u1.save()

        # create a PendingUser, consistent with a new user request  
        p = PendingUser.objects.create(
            is_pi = False, info_json = json.dumps(self.postdoc_info_dict)
        )

        staff_approve_pending_user(p.pk)
        mock_send_account_pending_email_to_requester.assert_called_once()
        mock_send_approval_email_to_pi.assert_called_once()


    def test_pi_approval_for_own_new_group_creates_resources(self):
        '''
        Here we test the case where the PI (who was previously unknown)
        has confirmed by clicking on the email.  Here they are creating
        a group for themselves.  Check that we create a ResearchGroup,
        and a user for the PI
        '''
        # check that we have no ResearchGroup, etc. at the start:
        existing_rg = ResearchGroup.objects.all()
        self.assertEqual(len(existing_rg), 0)
        existing_finance_coord = FinancialCoordinator.objects.all()
        self.assertEqual(len(existing_finance_coord), 0)
        existing_users = get_user_model().objects.all()
        self.assertEqual(len(existing_users), 0)
        existing_cnap_users = CnapUser.objects.all()
        self.assertEqual(len(existing_cnap_users), 0)

        # create a PendingUser for this PI, consistent with a new user request  
        p = PendingUser.objects.create(
            is_pi = True, info_json = json.dumps(self.pi_info_dict)
        )
        pi_approve_pending_user(p.pk)

        # See that the various objects were created:        
        existing_rg = ResearchGroup.objects.all()
        self.assertEqual(len(existing_rg), 1)
        existing_finance_coord = FinancialCoordinator.objects.all()
        self.assertEqual(len(existing_finance_coord), 1)
        existing_users = get_user_model().objects.all()
        self.assertEqual(len(existing_users), 1)
        existing_cnap_users = CnapUser.objects.all()
        self.assertEqual(len(existing_cnap_users), 1)


    @mock.patch('main_app.tasks.send_account_confirmed_email_to_requester')
    def test_pi_approval_for_new_group_creates_resources(self, mock_send_account_confirmed_email_to_requester):
        '''
        Here we test the case where the PI (who was previously unknown)
        has confirmed by clicking on the email.  Check that we create a ResearchGroup,
        a user for the PI, and a user for the regular user (both a regular user and
        a CnapUser associating the 'base' user and the group).  Both the PI and regular
        user have a base user AND a CnapUser created

        (case 1)
        '''
        # check that we have no ResearchGroup, etc. at the start:
        existing_rg = ResearchGroup.objects.all()
        self.assertEqual(len(existing_rg), 0)
        existing_finance_coord = FinancialCoordinator.objects.all()
        self.assertEqual(len(existing_finance_coord), 0)
        existing_users = get_user_model().objects.all()
        self.assertEqual(len(existing_users), 0)
        existing_cnap_users = CnapUser.objects.all()
        self.assertEqual(len(existing_cnap_users), 0)

        # create a PendingUser for this PI, consistent with a new user request  
        p = PendingUser.objects.create(
            is_pi = False, info_json = json.dumps(self.postdoc_info_dict)
        )
        pi_approve_pending_user(p.pk)

        # See that the various objects were created: 
        # Note that two users were created-        
        existing_rg = ResearchGroup.objects.all()
        self.assertEqual(len(existing_rg), 1)
        existing_finance_coord = FinancialCoordinator.objects.all()
        self.assertEqual(len(existing_finance_coord), 1)
        existing_users = get_user_model().objects.all()
        self.assertEqual(len(existing_users), 2)
        existing_cnap_users = CnapUser.objects.all()
        self.assertEqual(len(existing_cnap_users), 2)

        mock_send_account_confirmed_email_to_requester.assert_called_once()

    @mock.patch('main_app.tasks.send_account_confirmed_email_to_requester')
    def test_pi_approves_addition_to_existing_group_properly_adds_new_user_case1(self, mock_send_account_confirmed_email_to_requester):
        '''
        Here we imagine having an existing lab with the PI as the only user.  A new user
        (e.g. postdoc) associates with them.  The PI authorizes this by clicking 
        on the confirmation email.  Check that the new user (the one who made the request)
        is added to this existing group.
        '''
        # create a user who is a PI:
        pi_user = BaseUser.objects.create(
            first_name = 'John',
            last_name = 'Doe',
            email = settings.TEST_PI_EMAIL
        )

        # create their research group:
        org = Organization.objects.create(name=self.pi_info_dict['ORGANIZATION'])
        rg = ResearchGroup.objects.create(
            organization = org,
            pi_email = self.pi_info_dict['PI_EMAIL'],
            pi_name = '%s %s' % (self.pi_info_dict['PI_FIRST_NAME'], self.pi_info_dict['PI_LAST_NAME']),
            has_harvard_appointment = True if self.pi_info_dict['HARVARD_APPOINTMENT'].lower() == 'y' else False,
            department = self.pi_info_dict['DEPARTMENT'],
            address_lines = self.pi_info_dict['ADDRESS'],
            city = self.pi_info_dict['CITY'],
            state = self.pi_info_dict['STATE'],
            postal_code = self.pi_info_dict['POSTAL_CODE'],
            country = self.pi_info_dict['COUNTRY']
        )

        # associate those PI with their research group:
        u1 = CnapUser.objects.create(user=pi_user)
        u1.research_group.add(rg)
        u1.save()

        # confirm everything as expected prior to confirmation by the PI
        # click
        existing_rg = ResearchGroup.objects.all()
        self.assertEqual(len(existing_rg), 1)
        existing_users = get_user_model().objects.all()
        self.assertEqual(len(existing_users), 1)
        existing_cnap_users = CnapUser.objects.all()
        self.assertEqual(len(existing_cnap_users), 1)

        # create a PendingUser, consistent with a new user request  
        p = PendingUser.objects.create(
            is_pi = False, info_json = json.dumps(self.postdoc_info_dict)
        )

        pi_approve_pending_user(p.pk)

        # check that still have only 1 researchGroup,
        # but that there are now two users:
        existing_rg = ResearchGroup.objects.all()
        self.assertEqual(len(existing_rg), 1)
        existing_users = get_user_model().objects.all()
        self.assertEqual(len(existing_users), 2)
        existing_cnap_users = CnapUser.objects.all()
        self.assertEqual(len(existing_cnap_users), 2)
        mock_send_account_confirmed_email_to_requester.assert_called_once()

    @mock.patch('main_app.tasks.send_account_confirmed_email_to_requester')
    def test_pi_approves_addition_to_existing_group_properly_adds_new_user_case2(self, mock_send_account_confirmed_email_to_requester):
        '''
        Here we imagine having an existing lab with multiple users (i.e. some
        are NOT the PI).  A new user (e.g. postdoc) associates with them.  
        The PI authorizes this by clicking 
        on the confirmation email.  Check that the new user (the one who made the request)
        is added to this existing group.
        '''
        # create a user who is a PI:
        pi_user = BaseUser.objects.create(
            first_name = 'John',
            last_name = 'Doe',
            email = settings.TEST_PI_EMAIL
        )

        # create a user who is a postdoc
        postdoc_user = BaseUser.objects.create(
            first_name = 'Jane',
            last_name = 'Smith',
            email = settings.TEST_POSTDOC_EMAIL
        )

        # create their research group:
        org = Organization.objects.create(name=self.pi_info_dict['ORGANIZATION'])
        rg = ResearchGroup.objects.create(
            organization = org,
            pi_email = self.pi_info_dict['PI_EMAIL'],
            pi_name = '%s %s' % (self.pi_info_dict['PI_FIRST_NAME'], self.pi_info_dict['PI_LAST_NAME']),
            has_harvard_appointment = True if self.pi_info_dict['HARVARD_APPOINTMENT'].lower() == 'y' else False,
            department = self.pi_info_dict['DEPARTMENT'],
            address_lines = self.pi_info_dict['ADDRESS'],
            city = self.pi_info_dict['CITY'],
            state = self.pi_info_dict['STATE'],
            postal_code = self.pi_info_dict['POSTAL_CODE'],
            country = self.pi_info_dict['COUNTRY']
        )

        # associate those PI with their research group:
        u1 = CnapUser.objects.create(user=pi_user)
        u1.research_group.add(rg)
        u1.save()

        # associate the regular user (the postdoc):
        u2 = CnapUser.objects.create(user=postdoc_user)
        u2.research_group.add(rg)
        u2.save()

        # confirm everything as expected prior to confirmation by the PI
        # click
        existing_rg = ResearchGroup.objects.all()
        self.assertEqual(len(existing_rg), 1)
        existing_users = get_user_model().objects.all()
        self.assertEqual(len(existing_users), 2)
        existing_cnap_users = CnapUser.objects.all()
        self.assertEqual(len(existing_cnap_users), 2)

        # create a PendingUser, consistent with a new user request  
        p = PendingUser.objects.create(
            is_pi = False, info_json = json.dumps(self.gradstudent_info_dict)
        )

        pi_approve_pending_user(p.pk)

        # check that still have only 1 researchGroup,
        # but that there are now two users:
        existing_rg = ResearchGroup.objects.all()
        self.assertEqual(len(existing_rg), 1)
        existing_users = get_user_model().objects.all()
        self.assertEqual(len(existing_users), 3)
        existing_cnap_users = CnapUser.objects.all()
        self.assertEqual(len(existing_cnap_users), 3)
        mock_send_account_confirmed_email_to_requester.assert_called_once()

    @mock.patch('main_app.tasks.send_account_confirmed_email_to_requester')
    def test_pi_approves_addition_to_existing_group_properly_adds_new_user_case3(self, mock_send_account_confirmed_email_to_requester):
        '''
        Here we imagine having an existing lab with multiple users (i.e. some
        are NOT the PI).  A previously EXISTING user (e.g. postdoc from another lab) associates with them.  
        The PI authorizes this by clicking 
        on the confirmation email.  Check that the new user (the one who made the request)
        is added to this existing group.  However, also check that we did not create a new 
        user...we only create a new CnapUser to establish the relationship between the 'base'
        user and this ResearchGroup  
        '''
        # create a user who is a PI:
        pi_user = BaseUser.objects.create(
            first_name = 'John',
            last_name = 'Doe',
            email = settings.TEST_PI_EMAIL
        )

        # create a user who is a postdoc
        postdoc_user = BaseUser.objects.create(
            first_name = 'Jane',
            last_name = 'Smith',
            email = settings.TEST_POSTDOC_EMAIL
        )

        # create a user who is a grad student
        grad_user = BaseUser.objects.create(
            first_name = 'Jim',
            last_name = 'Grad',
            email = settings.TEST_GRAD_STUDENT_EMAIL
        )

        # create the research group which will have the PI and grad student
        org = Organization.objects.create(name=self.pi_info_dict['ORGANIZATION'])
        rg = ResearchGroup.objects.create(
            organization = org,
            pi_email = self.pi_info_dict['PI_EMAIL'],
            pi_name = '%s %s' % (self.pi_info_dict['PI_FIRST_NAME'], self.pi_info_dict['PI_LAST_NAME']),
            has_harvard_appointment = True if self.pi_info_dict['HARVARD_APPOINTMENT'].lower() == 'y' else False,
            department = self.pi_info_dict['DEPARTMENT'],
            address_lines = self.pi_info_dict['ADDRESS'],
            city = self.pi_info_dict['CITY'],
            state = self.pi_info_dict['STATE'],
            postal_code = self.pi_info_dict['POSTAL_CODE'],
            country = self.pi_info_dict['COUNTRY']
        )

        # create a research group for the old group the postdoc was
        # associated with:
        old_org = Organization.objects.create(name=self.old_pi_info_dict['ORGANIZATION'])
        old_rg = ResearchGroup.objects.create(
            organization = old_org,
            pi_email = self.old_pi_info_dict['PI_EMAIL'],
            pi_name = '%s %s' % (self.old_pi_info_dict['PI_FIRST_NAME'], self.old_pi_info_dict['PI_LAST_NAME']),
            has_harvard_appointment = True if self.old_pi_info_dict['HARVARD_APPOINTMENT'].lower() == 'y' else False,
            department = self.old_pi_info_dict['DEPARTMENT'],
            address_lines = self.old_pi_info_dict['ADDRESS'],
            city = self.old_pi_info_dict['CITY'],
            state = self.old_pi_info_dict['STATE'],
            postal_code = self.old_pi_info_dict['POSTAL_CODE'],
            country = self.old_pi_info_dict['COUNTRY']
        )

        # associate those PI with their research group:
        u1 = CnapUser.objects.create(user=pi_user)
        u1.research_group.add(rg)
        u1.save()

        # associate the regular user (the grad student):
        u2 = CnapUser.objects.create(user=grad_user)
        u2.research_group.add(rg)
        u2.save()

        # associate the postdoc with their old lab:
        u3 = CnapUser.objects.create(user=postdoc_user)
        u3.research_group.add(old_rg)
        u3.save()

        # confirm everything as expected prior to confirmation by the PI
        # click
        existing_rg = ResearchGroup.objects.all()
        self.assertEqual(len(existing_rg), 2)
        existing_users = get_user_model().objects.all()
        self.assertEqual(len(existing_users), 3)
        existing_cnap_users = CnapUser.objects.all()
        self.assertEqual(len(existing_cnap_users), 3)

        # create a PendingUser, consistent with a new user request  
        p = PendingUser.objects.create(
            is_pi = False, info_json = json.dumps(self.postdoc_info_dict)
        )

        pi_approve_pending_user(p.pk)

        # check that there are still only 2 groups, and 3 regular
        # users, but now 4 cnap users
        existing_rg = ResearchGroup.objects.all()
        self.assertEqual(len(existing_rg), 2)
        existing_users = get_user_model().objects.all()
        self.assertEqual(len(existing_users), 3)
        existing_cnap_users = CnapUser.objects.all()
        self.assertEqual(len(existing_cnap_users), 4)
        mock_send_account_confirmed_email_to_requester.assert_called_once()

    @mock.patch('main_app.tasks.fetch_emails')
    @mock.patch('main_app.tasks.get_email_body')
    @mock.patch('main_app.tasks.inform_staff_of_new_account')
    def test_full_account_request_case1(self, mock_inform_staff_of_new_account, mock_get_email_body, mock_fetch_emails):
        '''
        Technically not a "unit" test.  Tests the full set of operations following the
        parsing of the email body until the email is sent to QBRC for approval

        This is for the case where we have a new user trying to register
        with a new lab
        '''
        # does not matter what this is, except that it 
        # has a length that is a multiple of 2
        mock_fetch_emails.return_value = ['a','b']
        mock_get_email_body.return_value = '''
            <html>
            <head>
            <meta http-equiv="Content-Type" content="text/html; charset=us-ascii">
            </head>
            <body>
            FIRST_NAME:Jane <br>
            LAST_NAME:Postdoc <br>
            EMAIL:%s <br>
            PHONE:6171231234 <br>
            PI: No <br>
            PI_FIRST_NAME:Alice <br>
            PI_LAST_NAME:Prof <br>
            PI_EMAIL:%s <br>
            PI_PHONE:6171231234 <br>
            HARVARD_APPOINTMENT: <br>
            ORGANIZATION:Harvard School of Public Health <br>
            DEPARTMENT:Biostatistics <br>
            FINANCIAL_CONTACT:John Money<br>
            FINANCIAL_EMAIL:%s <br>
            ADDRESS:677 Huntington Ave Bldg 2, R410 <br>
            CITY:Boston <br>
            STATE:MA <br>
            POSTAL_CODE:02115 <br>
            COUNTRY:United States
            </body>
            </html>
        ''' % (settings.TEST_POSTDOC_EMAIL, settings.TEST_PI_EMAIL, settings.TEST_FINANCE_EMAIL)

        # ensure we start from zero pending users
        p = PendingUser.objects.all()
        self.assertEqual(len(p), 0)

        process_emails(None, [100,], ACCOUNT_REQUEST)

        p = PendingUser.objects.all()
        self.assertEqual(len(p), 1)
        mock_inform_staff_of_new_account.assert_called_once()

    @mock.patch('main_app.tasks.fetch_emails')
    @mock.patch('main_app.tasks.get_email_body')
    @mock.patch('main_app.tasks.send_approval_email_to_pi')
    @mock.patch('main_app.tasks.send_account_pending_email_to_requester')
    def test_full_account_request_case2(self, 
        mock_send_account_pending_email_to_requester, 
        mock_send_approval_email_to_pi,
        mock_get_email_body, mock_fetch_emails):
        '''
        Technically not a "unit" test.  Tests the full set of operations following the
        parsing of the email body until the email is sent to QBRC for approval

        This is for the case where we have a new user trying to register
        with an existing lab
        '''
        # does not matter what this is, except that it 
        # has a length that is a multiple of 2
        mock_fetch_emails.return_value = ['a','b']
        mock_get_email_body.return_value = '''
            <html>
            <head>
            <meta http-equiv="Content-Type" content="text/html; charset=us-ascii">
            </head>
            <body>
            FIRST_NAME:Jane <br>
            LAST_NAME:Postdoc <br>
            EMAIL:%s <br>
            PHONE:6171231234 <br>
            PI: No <br>
            PI_FIRST_NAME:Alice <br>
            PI_LAST_NAME:Prof <br>
            PI_EMAIL:%s <br>
            PI_PHONE:6171231234 <br>
            HARVARD_APPOINTMENT: <br>
            ORGANIZATION:Harvard School of Public Health <br>
            DEPARTMENT:Biostatistics <br>
            FINANCIAL_CONTACT:John Money<br>
            FINANCIAL_EMAIL:%s <br>
            ADDRESS:677 Huntington Ave Bldg 2, R410 <br>
            CITY:Boston <br>
            STATE:MA <br>
            POSTAL_CODE:02115 <br>
            COUNTRY:United States
            </body>
            </html>
        ''' % (settings.TEST_POSTDOC_EMAIL, settings.TEST_PI_EMAIL, settings.TEST_FINANCE_EMAIL)


        # ensure we start from zero pending users
        p = PendingUser.objects.all()
        self.assertEqual(len(p), 0)

        # create the lab:
        pi_user = BaseUser.objects.create(
            first_name = 'John',
            last_name = 'Doe',
            email = settings.TEST_PI_EMAIL
        )

        # create the research group:
        org = Organization.objects.create(name=self.pi_info_dict['ORGANIZATION'])
        rg = ResearchGroup.objects.create(
            organization = org,
            pi_email = self.pi_info_dict['PI_EMAIL'],
            pi_name = '%s %s' % (self.pi_info_dict['PI_FIRST_NAME'], self.pi_info_dict['PI_LAST_NAME']),
            has_harvard_appointment = True if self.pi_info_dict['HARVARD_APPOINTMENT'].lower() == 'y' else False,
            department = self.pi_info_dict['DEPARTMENT'],
            address_lines = self.pi_info_dict['ADDRESS'],
            city = self.pi_info_dict['CITY'],
            state = self.pi_info_dict['STATE'],
            postal_code = self.pi_info_dict['POSTAL_CODE'],
            country = self.pi_info_dict['COUNTRY']
        )

        # associate those users with the research group:
        u1 = CnapUser.objects.create(user=pi_user)
        u1.research_group.add(rg)
        u1.save()

        # now that the lab exists, we initiate the process
        process_emails(None, [100,], ACCOUNT_REQUEST)

        p = PendingUser.objects.all()
        self.assertEqual(len(p), 1)
        mock_send_account_pending_email_to_requester.assert_called_once() 
        mock_send_approval_email_to_pi.assert_called_once()

class PipelineRequestTestCase(TestCase):
    '''
    Tests the functionality/logic of the pipeline request workflow
    '''
    def setUp(self):
        pass
    
    def tearDown(self):
        pass

class QualtricsSurveyTestCase(TestCase):
    '''
    This test class covers operations performed as part of querying
    the QBRC mailbox for survey results generated by the Qualtrics platform
    '''
    def setUp(self):
        pass
    
    def tearDown(self):
        pass


    @mock.patch('main_app.tasks.imaplib')
    def test_unreachable_imap_server_raises_ex(self, mock_imaplib):
        '''
        This covers the case where the initial query to the imap server
        does not work because the mail server is down, internet is not responding, etc.
        '''
        mock_class_inst_that_raises_ex = mock.MagicMock(side_effect=Exception('Some imaplib ex!'))
        mock_imaplib.IMAP4_SSL.return_value = mock_class_inst_that_raises_ex

        with self.assertRaises(MailQueryException):
            get_mailbox()

    @mock.patch('main_app.tasks.imaplib')
    def test_cannot_login_to_imap_server_raises_ex(self, mock_imaplib):
        '''
        This covers the situation where we can contact the imap server
        but it does not login for whatever reason
        '''
        mock_imap_ssl_class = mock.MagicMock()
        mock_imap_ssl_class.login.side_effect = Exception('Could not login')
        mock_imaplib.IMAP4_SSL.return_value = mock_imap_ssl_class

        with self.assertRaises(MailQueryException):
            get_mailbox()

    @mock.patch('main_app.tasks.imaplib')
    def test_imap_mailbox_select_fails_raises_ex(self, mock_imaplib):
        '''
        This covers the test where you cannot select the mailbox(maybe its name was changed?)
        '''
        mock_imap_ssl_class = mock.MagicMock()
        mock_imap_ssl_class.select.side_effect = Exception('Could not select mailbox')
        mock_imaplib.IMAP4_SSL.return_value = mock_imap_ssl_class

        with self.assertRaises(MailQueryException):
            get_mailbox()

    @mock.patch('main_app.tasks.get_mailbox')
    @mock.patch('main_app.tasks.handle_exception')
    def test_imap_problem_informs_admins(self, mock_handle_ex, mock_get_mailbox):
        '''
        The get_mailbox function will raise a MailQueryException if 
        anything goes wrong(as tested above).  Test that a get_mailbox
        raising an exception triggers notification of the admins
        '''
        mock_get_mailbox.side_effect = MailQueryException('Problem!')
        check_for_qualtrics_survey_results()
        mock_handle_ex.assert_called_once()


    @mock.patch('main_app.tasks.get_mailbox')
    @mock.patch('main_app.tasks.handle_exception')
    def test_imap_search_function_failure_informs_admins(self, mock_handle_ex, mock_get_mailbox):
        '''
        This tests that we have obtained a valid mailbox, but the 
        search for messages issues an error (maybe a dropped connection or 
        similar)
        '''
        mock_mailbox = mock.MagicMock()
        mock_mailbox.search.side_effect = MailQueryException('Problem!')
        mock_get_mailbox.return_value = mock_mailbox
        check_for_qualtrics_survey_results()
        mock_handle_ex.assert_called_once()