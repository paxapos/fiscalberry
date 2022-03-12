# coding=utf-8

import tornado.httpserver
import tornado.web
import socket
import json
import jwt
import datetime
import logging
from tornado.options import define, options
from ApiRest.Auth import jwtauth, AuthConfig
from Traductores.TraductoresHandler import TraductoresHandler, TraductorException

import time

#HTTP_STATUS
HTTP_CODE_OK = 200
HTTP_CODE_NOT_FOUND = 404
HTTP_CODE_FORBIDDEN = 401 
HTTP_CODE_BAD_REQUEST = 400
HTTP_CODE_NOT_METHOD = 405
HTTP_CODE_INTERNAL_ERROR = 500

#
# API REST AUTH CONTROLLER
#
class AuthHandler(tornado.web.RequestHandler):
    def initialize(self):
        self.config= AuthConfig()
    
    def prepare(self):
        if self.request.headers["Content-Type"].startswith("application/json"):
            self.body = json.loads(self.request.body)
        else:
            self.body = None        

    def post(self, *args, **kwargs):
        response = {}
        body= self.body
        try:
            users= self.config.get_users()
            if not('user' in body and 'key' in body):
                response = {'err': 'Campos Incorrectos'}
                self.set_status(HTTP_CODE_BAD_REQUEST)           
            elif users.has_key(body['user']) and users[body['user']]['key'] == body['key']:
                logging.info("Creando Token de Acceso")
                #Encode a new token with JSON Web Token (PyJWT)
                seconds= int(self.config.get_expire_time())
                self.encoded = jwt.encode({
                    'some': body['user'],
                    'exp': datetime.datetime.utcnow() + datetime.timedelta(seconds=seconds)},
                    self.config.get_secret_key(),
                    algorithm='HS256'
                )
                #return the generated token        
                response = {'token': self.encoded.decode('ascii')}
            else:
                response = {'err': 'Usuario Incorrecto'}
                self.set_status(HTTP_CODE_BAD_REQUEST)
        except Exception as e:
            self.set_status(HTTP_CODE_INTERNAL_ERROR)
            errtxt = repr(e) + "- " + str(e)
            logging.error(errtxt)
            response["err"] = errtxt
            import sys, traceback
            traceback.print_exc(file=sys.stdout)
        print("escribiendo la respuesrta")
        print(response)
        self.write(response)

#
# API REST CONTROLLER
# DECORATOR TO VALIDATE AUTH
#
#@jwtauth
class ApiRestHandler(tornado.web.RequestHandler):
    def initialize(self):
        self.traductor = TraductoresHandler(self)

    def prepare(self):
        if self.request.headers["Content-Type"].startswith("application/json"):
            self.body = json.loads(self.request.body)
        else:
            self.body = None

    def post(self):
        traductor = self.traductor
        body = self.body
        response = {}
        logging.getLogger("ApiRestHandler").info(f"Request \n -> {body}")

        try:
            response = traductor.json_to_comando(body)
        except TypeError as e:
            self.set_status(HTTP_CODE_BAD_REQUEST)
            errtxt = "Error parseando el JSON %s" % e
            logging.error(errtxt)
            response["err"] = errtxt
            import sys, traceback
            traceback.print_exc(file=sys.stdout)

        except TraductorException as e:
            self.set_status(HTTP_CODE_NOT_METHOD)
            errtxt = "Traductor Comandos: %s" % str(e)
            logging.error(errtxt)
            response["err"] = errtxt
            import sys, traceback
            traceback.print_exc(file=sys.stdout)

        except KeyError as e:
            self.set_status(HTTP_CODE_NOT_METHOD)
            logging.info("Comando")
            errtxt = "El comando no es valido para ese tipo de impresora: %s" % e
            logging.error(errtxt)
            response["err"] = errtxt
            import sys, traceback
            traceback.print_exc(file=sys.stdout)

        except socket.error as err:
            self.set_status(HTTP_CODE_INTERNAL_ERROR)
            import errno
            errtxt = "Socket error: %s" % err
            logging.error(errtxt)
            response["err"] = errtxt
            import sys, traceback
            traceback.print_exc(file=sys.stdout)
            
        except Exception as e:
            self.set_status(HTTP_CODE_INTERNAL_ERROR)
            errtxt = repr(e) + "- " + str(e)
            logging.error(errtxt)
            response["err"] = errtxt
            import sys, traceback
            traceback.print_exc(file=sys.stdout)

        logging.getLogger("ApiRestHandler").info("Response \n <- %s" % response)
        self.write(response)