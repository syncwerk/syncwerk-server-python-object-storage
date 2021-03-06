import os
import ConfigParser
import binascii
import logging
import json

from objectstorage.exceptions import InvalidConfigError
from objectstorage.backends.filesystem import SyncwObjStoreFS

def get_ceph_conf(cfg, section):
    config_file = cfg.get(section, 'ceph_config')
    pool_name = cfg.get(section, 'pool')
    ceph_client_id = ''
    if cfg.has_option(section, 'ceph_client_id'):
        ceph_client_id = cfg.get(section, 'ceph_client_id')

    from objectstorage.backends.ceph import CephConf

    return CephConf(config_file, pool_name, ceph_client_id)

def get_s3_conf(cfg, section):
    key_id = cfg.get(section, 'key_id')
    key = cfg.get(section, 'key')
    bucket = cfg.get(section, 'bucket')

    host = None
    port = None
    if cfg.has_option(section, 'host'):
        addr = cfg.get(section, 'host')

        segs = addr.split(':')
        host = segs[0]

        try:
            port = int(segs[1])
        except IndexError:
            pass

    use_v4_sig = False
    if cfg.has_option(section, 'use_v4_signature'):
        use_v4_sig = cfg.getboolean(section, 'use_v4_signature')

    aws_region = None
    if use_v4_sig:
        if not cfg.has_option(section, 'aws_region'):
            raise InvalidConfigError('aws_region is not configured')
        aws_region = cfg.get(section, 'aws_region')

    from objectstorage.backends.s3 import S3Conf
    conf = S3Conf(key_id, key, bucket, host, port, use_v4_sig, aws_region)

    return conf

def get_s3_conf_from_json(cfg):
    key_id = cfg['key_id']
    key = cfg['key']
    bucket = cfg['bucket']

    host = None
    port = None

    if cfg.has_key('host'):
        addr = cfg['host']

        segs = addr.split(':')
        host = segs[0]

        try:
            port = int(segs[1])
        except IndexError:
            pass
    use_v4_sig = False
    if cfg.has_key('use_v4_signature'):
        use_v4_sig = cfg['use_v4_signature'].lower() == 'true'

    aws_region = None
    if use_v4_sig:
        if not cfg.has_key('aws_region'):
            raise InvalidConfigError('aws_region is not configured')
        aws_region = cfg('aws_region')

    from objectstorage.backends.s3 import S3Conf
    conf = S3Conf(key_id, key, bucket, host, port, use_v4_sig, aws_region)

    return conf

def get_oss_conf(cfg, section):
    key_id = cfg.get(section, 'key_id')
    key = cfg.get(section, 'key')
    bucket = cfg.get(section, 'bucket')
    endpoint = ''
    if cfg.has_option(section, 'endpoint'):
        endpoint = cfg.get(section, 'endpoint')
    if not endpoint:
        region = cfg.get(section, 'region')
        endpoint = 'oss-cn-%s-internal.aliyuncs.com' % region

    host = endpoint

    from objectstorage.backends.alioss import OSSConf
    conf = OSSConf(key_id, key, bucket, host)

    return conf

def get_swift_conf(cfg, section):
    user_name = cfg.get(section, 'user_name')
    password = cfg.get(section, 'password')
    container = cfg.get(section, 'container')
    auth_host = cfg.get(section, 'auth_host')
    if not cfg.has_option(section, 'auth_ver'):
        auth_ver = 'v2.0'
    else:
        auth_ver = cfg.get(section, 'auth_ver')
    if auth_ver != 'v1.0':
        tenant = cfg.get(section, 'tenant')
    else:
        tenant = None
    if cfg.has_option(section, 'use_https'):
        use_https = cfg.getboolean(section, 'use_https')
    else:
        use_https = False
    if cfg.has_option(section, 'region'):
        region = cfg.get(section, 'region')
    else:
        region = None
    if cfg.has_option(section, 'domain'):
        domain = cfg.get(section, 'domain')
    else:
        domain = 'default'

    from objectstorage.backends.swift import SwiftConf
    conf = SwiftConf(user_name, password, container, auth_host, auth_ver, tenant, use_https, region, domain)
    return conf

def get_swift_conf_from_json (cfg):
    user_name = cfg['user_name']
    password = cfg['password']
    container = cfg['container']
    auth_host = cfg['auth_host']
    if not cfg.has_key('auth_ver'):
        auth_ver = 'v2.0'
    else:
        auth_ver = cfg['auth_ver']
    if auth_ver != 'v1.0':
        tenant = cfg['tenant']
    else:
        tenant = None
    if cfg.has_key('use_https') and cfg['use_https'].lower() == 'true':
        use_https = True
    else:
        use_https = False
    if cfg.has_key('region'):
        region = cfg['region']
    else:
        region = None
    if cfg.has_key('domain'):
        domain = cfg['domain']
    else:
        domain = 'default'

    from objectstorage.backends.swift import SwiftConf
    conf = SwiftConf(user_name, password, container, auth_host, auth_ver, tenant, use_https, region, domain)
    return conf

class SyncwerkConfig(object):
    def __init__(self):
        self.cfg = None
        self.syncwerk_conf_dir = os.environ['SYNCWERK_CONF_DIR']
        self.central_config_dir = os.environ.get('SYNCWERK_CENTRAL_CONF_DIR',
                                                 None)
        confdir = self.central_config_dir or self.syncwerk_conf_dir
        self.syncwerk_conf = os.path.join(confdir, 'server.conf')

    def get_config_parser(self):
        if self.cfg is None:
            self.cfg = ConfigParser.ConfigParser()
            try:
                self.cfg.read(self.syncwerk_conf)
            except Exception, e:
                raise InvalidConfigError(str(e))
        return self.cfg

    def get_syncw_crypto(self):
        if not self.cfg.has_option('store_crypt', 'key_path'):
            return None
        key_path = self.cfg.get('store_crypt', 'key_path')
        if not os.path.exists(key_path):
            raise InvalidConfigError('key file %s doesn\'t exist' % key_path)

        key_config = ConfigParser.ConfigParser()
        key_config.read(key_path)
        if not key_config.has_option('store_crypt', 'enc_key') or not \
           key_config.has_option('store_crypt', 'enc_iv'):
            raise InvalidConfigError('Invalid key file %s: incomplete info' % key_path)

        hex_key = key_config.get('store_crypt', 'enc_key')
        hex_iv = key_config.get('store_crypt', 'enc_iv')
        raw_key = binascii.a2b_hex(hex_key)
        raw_iv = binascii.a2b_hex(hex_iv)

        from objectstorage.utils.crypto import SyncwCrypto
        return SyncwCrypto(raw_key, raw_iv)

    def get_syncwerk_storage_dir(self):
        ccnet_conf_dir = os.environ.get('CCNET_CONF_DIR', '')
        if ccnet_conf_dir:
            syncwerk_ini = os.path.join(ccnet_conf_dir, 'storage.ini')
            if not os.access(syncwerk_ini, os.F_OK):
                raise RuntimeError('%s does not exist', syncwerk_ini)

            with open(syncwerk_ini) as f:
                syncwerk_data_dir = f.readline().rstrip()
                return os.path.join(syncwerk_data_dir, 'storage')
        else:
            # In order to pass test, if not set CCNET_CONF_DIR env, use follow path
            return os.path.join(self.syncwerk_conf_dir, 'storage')

class SyncwObjStoreFactory(object):
    obj_section_map = {
        'blocks': 'block_backend',
        'fs': 'fs_object_backend',
        'commits': 'commit_object_backend',
    }
    def __init__(self, cfg=None):
        self.syncwerk_cfg = cfg or SyncwerkConfig()
        self.json_cfg = None
        self.enable_storage_classes = False
        self.obj_stores = {'commits': {}, 'fs': {}, 'blocks': {}}

        cfg = self.syncwerk_cfg.get_config_parser()
        if cfg.has_option ('storage', 'enable_storage_classes'):
            enable_storage_classes = cfg.get('storage', 'enable_storage_classes')
            if enable_storage_classes.lower() == 'true':
                from objectstorage.db import init_db_session_class
                self.enable_storage_classes = True
                self.session = init_db_session_class(cfg)
                try:
                    json_file = cfg.get('storage', 'storage_classes_file')
                    f = open(json_file)
                    self.json_cfg = json.load(f)
                except Exception:
                    logging.warning('Failed to load json file')
                    raise

    def get_obj_stores(self, obj_type):
        try:
            if self.obj_stores[obj_type]:
                return self.obj_stores[obj_type]
        except KeyError:
            raise RuntimeError('unknown obj_type ' + obj_type)

        for bend in self.json_cfg:
            storage_id = bend['storage_id']

            crypto = self.syncwerk_cfg.get_syncw_crypto()
            compressed = obj_type == 'fs'

            if bend[obj_type]['backend'] == 'fs':
                obj_dir = os.path.join(bend[obj_type]['dir'], 'storage', obj_type)
                self.obj_stores[obj_type][storage_id] = SyncwObjStoreFS(compressed, obj_dir, crypto)
            elif bend[obj_type]['backend'] == 'swift':
                from objectstorage.backends.swift import SyncwObjStoreSwift
                swift_conf = get_swift_conf_from_json(bend[obj_type])
                self.obj_stores[obj_type][storage_id] = SyncwObjStoreSwift(compressed, swift_conf, crypto)
            elif bend[obj_type]['backend'] == 's3':
                from objectstorage.backends.s3 import SyncwObjStoreS3
                s3_conf = get_s3_conf_from_json(bend[obj_type])
                self.obj_stores[obj_type][storage_id] = SyncwObjStoreS3(compressed, s3_conf, crypto)
            else:
                raise InvalidConfigError('Unknown backend type: %s.' % bend[obj_type]['backend'])

            if bend.has_key('is_default') and bend['is_default']==True:
                if self.obj_stores[obj_type].has_key('__default__'):
                    raise InvalidConfigError('Only one default backend can be set.')
                self.obj_stores[obj_type]['__default__'] = self.obj_stores[obj_type][storage_id]

        return self.obj_stores[obj_type]

    def get_obj_store(self, obj_type):
        '''Return an implementation of SyncwerkObjStore'''
        cfg = self.syncwerk_cfg.get_config_parser()
        try:
            section = self.obj_section_map[obj_type]
        except KeyError:
            raise RuntimeError('unknown obj_type ' + obj_type)

        crypto = self.syncwerk_cfg.get_syncw_crypto()

        if cfg.has_option(section, 'name'):
            backend_name = cfg.get(section, 'name')
        else:
            backend_name = 'fs'

        compressed = obj_type == 'fs'
        if backend_name == 'fs':
            obj_dir = os.path.join(self.syncwerk_cfg.get_syncwerk_storage_dir(), obj_type)
            return SyncwObjStoreFS(compressed, obj_dir, crypto)

        elif backend_name == 's3':
            # We import s3 backend here to avoid depenedency on boto for users
            # not using s3
            from objectstorage.backends.s3 import SyncwObjStoreS3
            s3_conf = get_s3_conf(cfg, section)
            return SyncwObjStoreS3(compressed, s3_conf, crypto)

        elif backend_name == 'ceph':
            # We import ceph backend here to avoid depenedency on rados for
            # users not using rados
            from objectstorage.backends.ceph import SyncwObjStoreCeph
            ceph_conf = get_ceph_conf(cfg, section)
            return SyncwObjStoreCeph(compressed, ceph_conf, crypto)

        elif backend_name == 'oss':
            from objectstorage.backends.alioss import SyncwObjStoreOSS
            oss_conf = get_oss_conf(cfg, section)
            return SyncwObjStoreOSS(compressed, oss_conf, crypto)

        elif backend_name == 'swift':
            from objectstorage.backends.swift import SyncwObjStoreSwift
            swift_conf = get_swift_conf(cfg, section)
            return SyncwObjStoreSwift(compressed, swift_conf, crypto)

        else:
            raise InvalidConfigError('unknown %s backend "%s"' % (obj_type, backend_name))

objstore_factory = SyncwObjStoreFactory()
repo_storage_id = {}

def get_repo_storage_id(repo_id):
    if repo_storage_id.has_key(repo_id):
        return repo_storage_id[repo_id]
    else:
        from .db import Base
        from sqlalchemy.orm.scoping import scoped_session
        RepoStorageId = Base.classes.RepoStorageId
        storage_id = None
        session = scoped_session(objstore_factory.session)
        q = session.query(RepoStorageId).filter(RepoStorageId.repo_id==repo_id)
        r = q.first()
        storage_id = r.storage_id if r else None
        repo_storage_id[repo_id] = storage_id
        session.remove()
        return storage_id
