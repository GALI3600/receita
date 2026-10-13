import os

# A suíte roda como development (SECRET_KEY de desenvolvimento, cookie sem Secure, e-mails no
# log). Precisa vir antes de qualquer import do app: as settings são lidas no import.
os.environ["ENVIRONMENT"] = "development"
