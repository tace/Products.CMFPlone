from zope.interface import Interface
from zope.component import getUtility

from zope import schema
from zope.formlib import form
from zope.app.form.browser import TextWidget, CheckBoxWidget, ASCIIWidget
from zope.app.form.interfaces import WidgetInputError, InputErrors

#from plone.app.controlpanel import PloneMessageFactory as _

from AccessControl import getSecurityManager
from Products.CMFCore.interfaces import ISiteRoot
from Products.CMFCore.utils import getToolByName
from Products.CMFPlone import PloneMessageFactory as _

from Products.Five.formlib.formbase import PageForm
from ZODB.POSException import ConflictError

from Products.statusmessages.interfaces import IStatusMessage

from plone.app.users.userdataschema import IUserDataSchemaProvider

from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile

from plone.app.controlpanel.widgets import MultiCheckBoxVocabularyWidget

from zope.schema.vocabulary import SimpleVocabulary
from zope.app.component.hooks import getSite
from plone.protect import CheckAuthenticator

# Define constants from the Join schema that should be added to the
# vocab of the join fields setting in usergroupssettings controlpanel.
JOIN_CONST = ['username', 'password', 'email', 'mail_me']


class IRegisterSchema(Interface):

    username = schema.ASCIILine(
        title=_(u'label_user_name', default=u'User Name'),
        description=_(u'help_user_name_creation_casesensitive',
                      default=u"Enter a user name, usually something "
                               "like 'jsmith'. "
                               "No spaces or special characters. "
                               "Usernames and passwords are case sensitive, "
                               "make sure the caps lock key is not enabled. "
                               "This is the name used to log in."))

    password = schema.Password(
        title=_(u'label_password', default=u'Password'),
        description=_(u'help_password_creation',
                      default=u'Minimum 5 characters.'))

    password_ctl = schema.Password(
        title=_(u'label_confirm_password',
                default=u'Confirm password'),
        description=_(u'help_confirm_password',
                      default=u"Re-enter the password. "
                      "Make sure the passwords are identical."))

    mail_me = schema.Bool(
        title=_(u'label_mail_password',
                default=u"Send a mail with the password"),
        default=False)

class IAddUserSchema(Interface):

    groups = schema.List(title=_(u'label_add_to_groups', default=u'Add to the following groups:'),
                            description=u'',
                            required=False,
                            value_type=schema.Choice(vocabulary='Group Ids'))

def FullNameWidget(field, request):
    """Widget for fullname field.
    """
    field.description = _(
        u'help_full_name_creation',
        default=u"Enter full name, e.g. John Smith.")
    widget = TextWidget(field, request)
    return widget


def EmailWidget(field, request):
    """Widget for email field.

    Note that the email regular expression that is used for validation
    only allows ascii, so we also use the ASCIIWidget here.
    """
    field.description = _(
        u'help_email_creation',
        default = u"Enter an email address. "
        "This is necessary in case the password is lost. "
        "We respect your privacy, and will not give the address "
        "away to any third parties or expose it anywhere.")
    widget = ASCIIWidget(field, request)
    return widget


def EmailAsLoginWidget(field, request):
    """Widget for email field when emails are used as login names.
    """
    field.description = _(
        u'help_email_creation_for_login',
        default = u"Enter an email address. This will be your login name. "
        "We respect your privacy, and will not give the address away to any "
        "third parties or expose it anywhere.")
    widget = ASCIIWidget(field, request)
    return widget


class NoCheckBoxWidget(CheckBoxWidget):
    """ A widget used for _not_ displaying the checkbox.
    """

    def __call__(self):
        """Render the widget to HTML."""
        return ""


def CantChoosePasswordWidget(field, request):
    """ Change the mail_me field widget so it doesn't display the checkbox """

    field.title = u''
    field.readonly = True
    field.description = _(
        u'label_password_change_mail',
        default=u"A URL will be generated and e-mailed to you; "
        "follow the link to reach a page where you can change your "
        "password and complete the registration process.")
    widget = NoCheckBoxWidget(field, request)
    return widget

def getGroupIds(context):
    site = getSite()
    groups_tool = getToolByName(site, 'portal_groups')
    groups = groups_tool.getGroupIds()
    groups.remove('AuthenticatedUsers') # Omit virtual group
    return SimpleVocabulary.fromValues(groups)

class RegistrationForm(PageForm):

    """ Dynamically get fields from user data, through admin
        config settings.
    """

    label = _(u'heading_registration_form', default=u'Registration Form')
    description = u""
    template = ViewPageTemplateFile('pageform_no_portlets.pt')

    @property
    def form_fields(self):

        """ form_fields is dynamic in this form, to be able to handle
        different join styles.
        """

        portal = getUtility(ISiteRoot)
        portal_props = getToolByName(self.context, 'portal_properties')
        props = portal_props.site_properties
        use_email_as_login = props.getProperty('use_email_as_login')
        registration_fields = list(props.getProperty('user_registration_fields'))

        canSetOwnPassword = not portal.getProperty('validate_email', True)

        # Check on required join fields
        #
        if not 'username' in registration_fields and not use_email_as_login:
            registration_fields.insert(0, 'username')

        if 'username' in registration_fields and use_email_as_login:
            registration_fields.remove('username')

        if not 'email' in registration_fields:
            # Perhaps only when use_email_as_login is true, but also
            # for some other cases; the email field has always been
            # required.
            registration_fields.append('email')

        if canSetOwnPassword:
            # Add password if needed
            #
            if not 'password' in registration_fields:
                if 'username' in registration_fields:
                    base = registration_fields.index('username')
                else:
                    base = registration_fields.index('email')
                registration_fields.insert(base + 1, 'password')

            # Add password_ctl after password
            #
            if not 'password_ctl' in registration_fields:
                registration_fields.insert(registration_fields.index('password') + 1,
                                   'password_ctl')

            # Add email_me after password_ctl
            #
            if not 'mail_me' in registration_fields:
                registration_fields.insert(registration_fields.index('password_ctl') + 1,
                                   'mail_me')

        # Can the user actually set his/her own password? If not, skip
        # password fields in final list.
        #
        if not canSetOwnPassword:
            if 'password' in registration_fields:
                del registration_fields[registration_fields.index('password')]
            if 'password_ctl' in registration_fields:
                del registration_fields[registration_fields.index('password_ctl')]

        # We need fields from both schemata here.
        #

        util = getUtility(IUserDataSchemaProvider)
        schema = util.getSchema()

        all_fields = form.Fields(schema) + form.Fields(IRegisterSchema)
         
        all_fields['fullname'].custom_widget = FullNameWidget
        if use_email_as_login:
            all_fields['email'].custom_widget = EmailAsLoginWidget
        else:
            all_fields['email'].custom_widget = EmailWidget

        if portal.validate_email:
            all_fields['mail_me'].custom_widget = CantChoosePasswordWidget
        
        # Pass the list of join form fields as a reference to the
        # Fields constructor, and return.
        #

        return form.Fields(*[all_fields[id] for id in registration_fields])

    # Actions validators
    def validate_registration(self, action, data):
        """
        specific business logic for this join form
        note: all this logic was taken directly from the old
        validate_registration.py script in
        Products/CMFPlone/skins/plone_login/join_form_validate.vpy
        """

        # CSRF protection
        CheckAuthenticator(self.request)

        registration = getToolByName(self.context, 'portal_registration')

        errors = super(RegistrationForm, self).validate(action, data)
        # ConversionErrors have no field_name attribute... :-(
        error_keys = [error.field_name for error in errors
                      if hasattr(error, 'field_name')]

        form_field_names = [f.field.getName() for f in self.form_fields]

        portal = getUtility(ISiteRoot)
        portal_props = getToolByName(self.context, 'portal_properties')
        props = portal_props.site_properties
        use_email_as_login = props.getProperty('use_email_as_login')

        # passwords should match
        if 'password' in form_field_names:
            assert('password_ctl' in form_field_names)
            # Skip this check if password fields already have an error
            if not ('password' in error_keys or \
                    'password_ctl' in error_keys):
                password = self.widgets['password'].getInputValue()
                password_ctl = self.widgets['password_ctl'].getInputValue()
                if password != password_ctl:
                    err_str = _(u'Passwords do not match.')
                    errors.append(WidgetInputError('password',
                                  u'label_password', err_str))
                    errors.append(WidgetInputError('password_ctl',
                                  u'label_password', err_str))
                    self.widgets['password'].error = err_str
                    self.widgets['password_ctl'].error = err_str


        # Password field should have a minimum length of 5
        if 'password' in form_field_names:
            # Skip this check if password fields already have an error
            if not 'password' in error_keys:
                password = self.widgets['password'].getInputValue()
                if len(password) < 5:
                    err_str = _(u'Passwords must contain at least 5 letters.')
                    errors.append(WidgetInputError(
                            'password', u'label_password', err_str))
                    self.widgets['password'].error = err_str


        username = ''
        email = ''
        try:
            email = self.widgets['email'].getInputValue()
        except InputErrors, exc:
            # WrongType?
            errors.append(exc)
        if use_email_as_login:
            username_field = 'email'
            username = email
        else:
            username_field = 'username'
            try:
                username = self.widgets['username'].getInputValue()
            except InputErrors, exc:
                errors.append(exc)

        # check if username is valid
        # Skip this check if username was already in error list
        if not username_field in error_keys:
            portal = getUtility(ISiteRoot)
            if username == portal.getId():
                err_str = _(u"This username is reserved. Please choose a "
                            "different name.")
                errors.append(WidgetInputError(
                        username_field, u'label_username', err_str))
                self.widgets[username_field].error = err_str


        # check if username is allowed
        if not username_field in error_keys:
            if not registration.isMemberIdAllowed(username):
                err_str = _(u"The login name you selected is already in use "
                            "or is not valid. Please choose another.")
                errors.append(WidgetInputError(
                        username_field, u'label_username', err_str))
                self.widgets[username_field].error = err_str


        # Skip this check if email was already in error list
        if not 'email' in error_keys:
            if 'email' in form_field_names:
                if not registration.isValidEmail(email):
                    err_str = _(u'You must enter a valid email address.')
                    errors.append(WidgetInputError(
                            'email', u'label_email', err_str))
                    self.widgets['email'].error = err_str

        return errors

    @form.action(_(u'label_register', default=u'Register'),
                 validator='validate_registration', name=u'register')
    def action_join(self, action, data):
        self.handle_join_success(data)
    
    def handle_join_success(self, data):
        portal = getUtility(ISiteRoot)
        registration = getToolByName(self.context, 'portal_registration')
        portal_props = getToolByName(self.context, 'portal_properties')
        props = portal_props.site_properties
        use_email_as_login = props.getProperty('use_email_as_login')

        if use_email_as_login:
            # The username field is not shown as the email is going to
            # be the username, but the field *is* needed further down
            # the line.
            data['username'] = data['email']
            # Set username in the form; at least needed for logging in
            # immediately when password reset is bypassed.
            self.request.form['form.username'] = data['email']

        username = data['username']

        password = data.get('password') or registration.generatePassword()

        if portal.validate_email or data.get('mail_me', 0):
            try:
                registration.registeredNotify(username)
            except ConflictError:
                # Let Zope handle this exception.
                raise
            except Exception:
                if portal.validate_email:
                    IStatusMessage(self.request).addStatusMessage(
                        _(u"Couldn't send mail"), type="error")

                    self.context.acl_users.userFolderDelUsers(
                        [username], REQUEST=self.request)
                    self.status = (
                        _(u'status_fatal_password_mail',
                          default=u"Failed to create your account: we were "
                          "unable to send your password to your email "
                          "address: ${address}",
                          mapping={u'address': data.get('email', '')}))
                    return
                else:
                    self.status = (
                        _(u'status_nonfatal_password_mail',
                          default=u"You account has been created, but we were "
                          "unable to send your password to your email "
                          "address: ${address}",
                          mapping={u'address': data.get('email', '')}))

        else:
            return self.context.unrestrictedTraverse('registered')()

class AddUserForm(RegistrationForm):

    label = _(u'heading_add_user_form', default=u'Add New User')
    description = u""

    @property
    def form_fields(self):
        defaultFields = super(AddUserForm, self).form_fields

        # Append the manager-focused fields
        allFields = defaultFields + form.Fields(IAddUserSchema)

        allFields['groups'].custom_widget = MultiCheckBoxVocabularyWidget

        return allFields

    @form.action(_(u'label_register', default=u'Register'),
                 validator='validate_registration', name=u'register')
    def action_join(self, action, data):
        errors = super(AddUserForm, self).handle_join_success(data)
        portal_groups = getToolByName(self.context, 'portal_groups')
        registration = getToolByName(self.context, 'portal_registration')

        securityManager = getSecurityManager()
        canManageUsers = securityManager.checkPermission('Manage users', self.context)
        username = data['username']
        password = data.get('password', None) or registration.generatePassword()

        try:
            registration.addMember(username, password, properties=data,
                                   REQUEST=self.request)

            # Add user to the selected group(s)
            if data.has_key('groups') and canManageUsers:
                add = data['groups']
                for groupname in add:
                    group = portal_groups.getGroupById(groupname)
                    group.addMember(username, REQUEST=self.request)

        except (AttributeError, ValueError), err:

            IStatusMessage(self.request).addStatusMessage(err, type="error")
            return

        IStatusMessage(self.request).addStatusMessage(
            _(u"User added."), type='info')
        self.request.response.redirect(self.context.absolute_url() + '/@@usergroup-userprefs')
