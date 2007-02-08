## Script (Python) "translate (alias for utranslate)"
##bind container=container
##bind context=context
##bind namespace=
##bind script=script
##bind subpath=traverse_subpath
##parameters=msgid, mapping={}, default=None, domain='plone', target_language=None, escape_for_js=False

from Products.CMFCore.utils import getToolByName

# handle the possible "nothing" condition in folder_contents.pt ln 21 gracefully
if msgid == None:
    return None

# get tool
tool = getToolByName(context, 'translation_service')

# this returns type unicode
value = tool.utranslate(domain,
                        msgid,
                        mapping,
                        context=context,
                        target_language=target_language,
                        default=default)

if not value and default is None:
    value = msgid

    for k, v in mapping.items():
        value = value.replace('${%s}' % k, v)

if escape_for_js:
    value = value.replace("'", "\\'")

return value
