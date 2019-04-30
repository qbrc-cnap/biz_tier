import unittest.mock as mock

from django.test import TestCase

from main_app.tasks import MailQueryException, \
    get_mailbox

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
        pass

    def test_empty_survey_response_is_ok(self):
        '''
        Some of the survey results can be emailed as empty, e.g. the "OTHER"
        key below:

        FOO:bar
        OTHER:
        SOMETHING:1
        '''
        pass


class AccountRequestTestCase(TestCase):
    '''
    Tests the functionality/logic of the account request workflow
    '''
    def setUp(self):
        pass
    
    def tearDown(self):
        pass


    def test_repeated_account_request_by_pi(self):
        '''
        This covers the case where a PI (who already has a ResearchGroup)
        makes another request for an account.  Test that we just message them
        since there is nothing to do (they already have an acct)
        '''
        pass

    def test_existing_regular_user_goes_to_correct_handler(self):
        '''
        Simply tests that we hit the right 'main' method for the case
        where we have an existing user
        '''
        pass

    def test_new_regular_user_goes_to_correct_handler(self):
        '''
        Simply tests that we hit the right 'main' method for the case
        where we have a new regular user
        '''
        pass

    def test_new_pi_goes_to_correct_handler(self):
        '''
        Simply tests that we hit the right 'main' method for the case
        where we have a new PI
        '''
        pass

    def test_existing_user_with_unknown_pi_goes_to_correct_method(self):
        '''
        If we have an existing user, but there is no research group.  This might be the 
        case if we had a user who was previously with one lab.  They then change to a 
        new lab where the PI has NOT previously worked with us.  Thus, the postdoc is known
        to us, but their PI does NOT have an account

        (case 7)
        '''
        pass

    def test_existing_user_requesting_account_for_previously_associated_group_only_sends_email(self):
        '''
        This tests the case where a regular user effectively makes a duplicate request.

        Just send them a message saying they are already registered

        (case 5)
        '''
        pass

    def test_existing_user_associating_with_lab_new_to_them(self):
        '''
        This tests the case where a postdoc may switch labs.  We know about them from a 
        previous lab, but they switch to another lab that we work with.  Thus, we have 
        records of both the user and the lab, but they are NOT associated yet.

        Test that a PendingUser object is created and the PI of the new lab is
        informed for confirmation.

        (case 4)
        '''
        pass

    def test_new_user_with_new_pi_starts_expected_process(self):
        '''
        Here we have a new user and a new PI.
        Test that we create a PendingUser and inform the QBRC staff

        (Case 1)
        '''
        pass

    def test_new_user_associating_new_pi(self):
        '''
        Here we have a new user attempting to associate with an existing lab.
        Test that the PendingUser instance is created, the pi is emailed for
        authorization, and the user is sent an email

        (case 2)
        '''
        pass

    def test_staff_approval_for_pi_self_request(self):
        '''
        Here we test that the QBRC has approved a request submitted
        by a PI for themself.

        Test that the PI is sent a confirmation email that they will
        click to finalize their account

        (part of case 3)
        '''
        pass

    def test_staff_approval_for_regular_user_request(self):
        '''
        Here we test that the activity once the QBRC has approved a request submitted
        by a regular user for a given lab

        Test that the PI is sent a confirmation email and the regular 
        user gets an info email.

        Also check that we do not (yet!) create any ResearchGroup and new user
        instances
        '''
        pass

    def test_pi_approval_for_own_new_group_creates_resources(self):
        '''
        Here we test the case where the PI (who was previously unknown)
        has confirmed by clicking on the email.  Here they are creating
        a group for themselves.  Check that we create a ResearchGroup,
        and a user for the PI
        '''
        pass

    def test_pi_approval_for_new_group_creates_resources(self):
        '''
        Here we test the case where the PI (who was previously unknown)
        has confirmed by clicking on the email.  Check that we create a ResearchGroup,
        a user for the PI, and a user for the regular user (both a regular user and
        a CnapUser associating the 'base' user and the group).  Both the PI and regular
        user have a base user AND a CnapUser created

        (case 1)
        '''
        pass

    def test_pi_approves_addition_to_existing_group_properly_adds_new_user_case1(self):
        '''
        Here we imagine having an existing lab with the PI as the only user.  A new user
        (e.g. postdoc) associates with them.  The PI authorizes this by clicking 
        on the confirmation email.  Check that the new user (the one who made the request)
        is added to this existing group.
        '''
        pass

    def test_pi_approves_addition_to_existing_group_properly_adds_new_user_case2(self):
        '''
        Here we imagine having an existing lab with multiple users (i.e. some
        are NOT the PI).  A new user (e.g. postdoc) associates with them.  
        The PI authorizes this by clicking 
        on the confirmation email.  Check that the new user (the one who made the request)
        is added to this existing group.
        '''
        pass

    def test_pi_approves_addition_to_existing_group_properly_adds_new_user_case3(self):
        '''
        Here we imagine having an existing lab with multiple users (i.e. some
        are NOT the PI).  A previously EXISTING user (e.g. postdoc from another lab) associates with them.  
        The PI authorizes this by clicking 
        on the confirmation email.  Check that the new user (the one who made the request)
        is added to this existing group.  However, also check that we did not create a new 
        user...we only create a new CnapUser to establish the relationship between the 'base'
        user and this ResearchGroup  
        '''
        pass

    def test_instantiation_of_research_group_creates_pi_as_cnap_user(self):
        '''
        Here we directly test that when we call the instantiate_new_research_group
        function, we create the ResearchGroup, FinanceCoordinator, and PI

        We need to create a 'base' user for the PI and also a CnapUser
        '''
        pass



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
    @mock.patch('main_app.tasks.handle_exception')
    def test_unreachable_imap_server_informs_admins(self, mock_handle_ex, mock_imaplib):
        '''
        This covers the case where the initial query to the imap server
        does not work because the mail server is down, internet is not responding, etc.
        '''
        mock_class_inst_that_raises_ex = mock.MagicMock(side_effect=Exception('Some imaplib ex!'))
        mock_imaplib.IMAP4_SSL.return_value = mock_class_inst_that_raises_ex

        with self.assertRaises(MailQueryException):
            get_mailbox()

        self.assertTrue(mock_handle_ex.called) # notification was sent

    @mock.patch('main_app.tasks.imaplib')
    @mock.patch('main_app.tasks.handle_exception')
    def test_cannot_login_to_imap_server_informs_admins(self, mock_handle_ex, mock_imaplib):
        '''
        This covers the situation where we can contact the imap server
        but it does not login for whatever reason
        '''
        mock_imap_ssl_class = mock.MagicMock()
        mock_imap_ssl_class.login.side_effect = Exception('Could not login')
        mock_imaplib.IMAP4_SSL.return_value = mock_imap_ssl_class

        with self.assertRaises(MailQueryException):
            get_mailbox()

        self.assertTrue(mock_handle_ex.called) # notification was sent

    @mock.patch('main_app.tasks.imaplib')
    @mock.patch('main_app.tasks.handle_exception')
    def test_imap_mailbox_select_fails_informs_admins(self, mock_handle_ex, mock_imaplib):
        '''
        This covers the test where you cannot select the mailbox(maybe its name was changed?)
        '''
        mock_imap_ssl_class = mock.MagicMock()
        mock_imap_ssl_class.select.side_effect = Exception('Could not select mailbox')
        mock_imaplib.IMAP4_SSL.return_value = mock_imap_ssl_class

        with self.assertRaises(MailQueryException):
            get_mailbox()

        self.assertTrue(mock_handle_ex.called) # notification was sent


    def test_imap_search_function_failure_informs_admins(self):
        pass

    def test_search_returns_empty_list(self):
        pass

    def test_email_parse_error_informs_admins(self):
        pass