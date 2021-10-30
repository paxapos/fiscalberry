# coding=utf-8
"""
    JSON Web Token auth for Tornado
"""
import jwt
import logging
import configparser

AUTHORIZATION_HEADER = 'Authorization'
AUTHORIZATION_METHOD = 'bearer'
#SECRET_KEY = "my_secret_key"
INVALID_HEADER_MESSAGE = "invalid header authorization"
MISSING_AUTHORIZATION_KEY = "Missing authorization"
AUTHORIZATION_ERROR_CODE = 401

jwt_options = {
    'verify_signature': True,
    'verify_exp': True,
    'verify_nbf': False,
    'verify_iat': True,
    'verify_aud': False
}

AUTH_FILE_NAME = "auth.ini"

#
# Auth Configuration
#
class AuthConfig:
    config = configparser.ConfigParser()

    def __init__(self):
        self.config.read(AUTH_FILE_NAME)

    def sections(self):
        return self.config.sections()

    def get_config(self):
        dictConf = {s: dict(self.config.items(s)) for s in self.config.sections()}
        return dictConf['config']

    def get_users(self):
        dictConf = {s: dict(self.config.items(s)) for s in self.config.sections()}
        return dictConf

    def get_secret_key(self):
        return self.config.get('config', 'secret_key')
    def get_expire_time(self):
        return self.config.get('config', 'expire_time')
#
# Handler Decorator
#
def is_valid_header(parts):
    """
        Validate the header
    """
    if parts[0].lower() != AUTHORIZATION_METHOD:
        return False
    elif len(parts) == 1:
        return False
    elif len(parts) > 2:
        return False

    return True

def return_auth_error(handler, message):
    """
        Return authorization error 
    """
    response= {}
    handler._transforms = []
    handler.set_status(AUTHORIZATION_ERROR_CODE)
    response['err']= message
    handler.write(response)
    handler.finish()

def return_header_error(handler):
    """
        Returh authorization header error
    """
    return_auth_error(handler, INVALID_HEADER_MESSAGE)

def jwtauth(handler_class):
    """
        Tornado JWT Auth Decorator
    """
    def wrap_execute(handler_execute):
        def require_auth(handler, kwargs):
            logging.info('Validando Token')
            config= AuthConfig()
            auth = handler.request.headers.get(AUTHORIZATION_HEADER)            
            if auth:
                parts = auth.split()
                if not is_valid_header(parts):
                    return_header_error(handler)
                token = parts[1]
                try:                   
                    jwt.decode(
                        token,
                        config.get_secret_key(),
                        options=jwt_options
                    )         
                except Exception as err:
                    return_auth_error(handler, str(err))

            else:
                handler._transforms = []
                handler.set_status(AUTHORIZATION_ERROR_CODE)
                handler.write(MISSING_AUTHORIZATION_KEY)
                handler.finish()

            return True

        def _execute(self, transforms, *args, **kwargs):

            try:
                require_auth(self, kwargs)
            except Exception:
                return False

            return handler_execute(self, transforms, *args, **kwargs)

        return _execute

    handler_class._execute = wrap_execute(handler_class._execute)
    return handler_class