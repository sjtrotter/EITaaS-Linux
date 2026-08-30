# Translations for EITaaS Connect

Run `xgettext --files-from=po/POTFILES.in --from-code=UTF-8 --language=Python --keyword=_ --package-name=eitaas-gui --package-version=0.1.0 --output=po/eitaas-gui.pot` from the repository root to refresh the template. No translations are shipped yet; the application uses `gettext.gettext`, so compiled `.mo` files installed under the `eitaas-gui` domain will be picked up once packaging binds the text domain.
