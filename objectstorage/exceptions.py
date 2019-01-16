#coding: UTF-8

class SyncwObjException(Exception):
    def __init__(self, msg):
        Exception.__init__(self)
        self.msg = msg

    def __str__(self):
        return self.msg

class InvalidConfigError(SyncwObjException):
    '''This Exception is rasied when error happens during parsing
    server.conf

    '''
    pass

class ObjectFormatError(SyncwObjException):
    '''This Exception is rasied when error happened during parse object
    format

    '''
    pass

class GetObjectError(SyncwObjException):
    '''This exception is raised when we failed to read object from backend.
    '''
    pass

class SwiftAuthenticateError(SyncwObjException):
    '''This exception is raised when failed to authenticate for swift.
    '''
    pass

class SyncwCryptoException(SyncwObjException):
    '''This exception is raised when crypto realted operation failed.
    '''
    pass
