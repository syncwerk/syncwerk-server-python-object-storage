import logging
import struct
import stat
import json
import binascii

from objectstorage.exceptions import ObjectFormatError
from objectstorage.utils import to_utf8

from .objstore_factory import objstore_factory
from .objstore_factory import get_repo_storage_id
from .blocks import block_mgr

ZERO_OBJ_ID = '0000000000000000000000000000000000000000'

SYNCW_METADATA_TYPE_FILE = 1
SYNCW_METADATA_TYPE_LINK = 2
SYNCW_METADATA_TYPE_DIR = 3

logger = logging.getLogger('objectstorage.fs')

class SyncwDirent(object):
    '''An entry in a SyncwDir'''
    DIR = 0
    FILE = 1
    def __init__(self, name, type, id, mtime, size):
        self.name = name
        self.type = type
        self.id = id
        self.mtime = mtime
        self.size = size

    def is_file(self):
        return self.type == SyncwDirent.FILE

    def is_dir(self):
        return self.type == SyncwDirent.DIR

    def __str__(self):
        return 'SyncwDirent(type=%s, name=%s, size=%s, id=%s, mtime=%s)' % \
            ('dir' if self.type == SyncwDirent.DIR else 'file', self.name, self.size, self.id, self.mtime)

    @staticmethod
    def fromV0(name, type, id):
        return SyncwDirent(name, type, id, -1, -1)

    @staticmethod
    def fromV1(name, type, id, mtime, size):
        return SyncwDirent(name, type, id, mtime, size)


class SyncwDir(object):
    def __init__(self, store_id, version, obj_id, dirents):
        self.version = version
        self.store_id = store_id
        self.obj_id = obj_id

        self.dirents = dirents

        self._cached_files_list = None
        self._cached_dirs_list = None

    def get_files_list(self):
        if self._cached_files_list is None:
            self._cached_files_list = [ dent for dent in self.dirents.itervalues() \
                                        if dent.type == SyncwDirent.FILE ]

        return self._cached_files_list

    def get_subdirs_list(self):
        if self._cached_dirs_list is None:
            self._cached_dirs_list = [ dent for dent in self.dirents.itervalues() \
                                        if dent.type == SyncwDirent.DIR ]

        return self._cached_dirs_list

    def lookup_dent(self, name):
        return self.dirents.get(name, None)

    def lookup(self, name):
        name = to_utf8(name)
        if name not in self.dirents:
            return None

        dent = self.dirents[name]
        if dent.is_dir():
            return fs_mgr.load_syncwdir(self.store_id, self.version, dent.id)
        else:
            return fs_mgr.load_syncwerk(self.store_id, self.version, dent.id)

    def remove_entry(self, name):
        if name in self.dirents:
            del self.dirents[name]

class SyncwFile(object):
    def __init__(self, store_id, version, obj_id, blocks, size):
        self.version = version
        self.store_id = store_id
        self.obj_id = obj_id

        self.blocks = blocks
        self.size = size

        self._content = None

    def get_stream(self):
        return SyncwerkStream(self)

    def get_content(self, limit=-1):
        if limit <= 0:
            limit = self.size
        if limit >= self.size:
            if self._content is None:
                stream = self.get_stream()
                self._content = stream.read(limit)
            return self._content
        else:
            stream = self.get_stream()
            return stream.read(limit)

class SyncwerkStream(object):
    '''Implements basic file-like interface'''
    def __init__(self, file_obj):
        self.file_obj = file_obj
        self.block = None
        self.block_idx = 0
        self.block_offset = 0

    def read(self, size):
        remain = size
        blocks = self.file_obj.blocks
        ret = ''

        while True:
            if not self.block or self.block_offset == len(self.block):
                if self.block_idx == len(blocks):
                    break
                self.block = block_mgr.load_block(self.file_obj.store_id,
                                                  self.file_obj.version,
                                                  blocks[self.block_idx])
                self.block_idx += 1
                self.block_offset = 0

            if self.block_offset + remain >= len(self.block):
                ret += self.block[self.block_offset:]
                remain -= (len(self.block) - self.block_offset)
                self.block_offset = len(self.block)
            else:
                ret += self.block[self.block_offset:self.block_offset+remain]
                self.block_offset += remain
                remain = 0

            if remain == 0:
                break

        return ret

    def close(self):
        pass

class SyncwFSManager(object):
    def __init__(self):
        if objstore_factory.enable_storage_classes:
            self.obj_stores = objstore_factory.get_obj_stores('fs')
        else:
            self.obj_store = objstore_factory.get_obj_store('fs')

        self._dir_counter = 0
        self._file_counter = 0

    def load_syncwerk(self, store_id, version, file_id):
        self._file_counter += 1

        blocks = []
        size = 0
        if file_id == ZERO_OBJ_ID:
            pass
        else:
            if not objstore_factory.enable_storage_classes:
                data = self.obj_store.read_obj(store_id, version, file_id)
            else:
                storage_id = get_repo_storage_id(store_id)
                if storage_id:
                    data = self.obj_stores[storage_id].read_obj(store_id, version, file_id)
                else:
                    data = self.obj_stores['__default__'].read_obj(store_id, version, file_id)

            if version == 0:
                blocks, size = self.parse_blocks_v0(data, file_id)
            elif version == 1:
                blocks, size = self.parse_blocks_v1(data, file_id)
            else:
                raise RuntimeError('invalid fs version ' + str(version))

        return SyncwFile(store_id, version, file_id, blocks, size)

    def load_syncwdir(self, store_id, version, dir_id, ret_unicode=False):
        self._dir_counter += 1

        dirents = {}
        if dir_id == ZERO_OBJ_ID:
            pass
        else:
            if not objstore_factory.enable_storage_classes:
                data = self.obj_store.read_obj(store_id, version, dir_id)
            else:
                storage_id = get_repo_storage_id(store_id)
                if storage_id:
                    data = self.obj_stores[storage_id].read_obj(store_id, version, dir_id)
                else:
                    data = self.obj_stores['__default__'].read_obj(store_id, version, dir_id)

            if version == 0:
                dirents = self.parse_dirents_v0(data, dir_id)
            elif version == 1:
                dirents = self.parse_dirents_v1(data, dir_id, ret_unicode)
            else:
                raise RuntimeError('invalid fs version ' + str(version))

        return SyncwDir(store_id, version, dir_id, dirents)

    def parse_dirents_v0(self, data, dir_id):
        '''binary format'''
        mode, = struct.unpack_from("!i", data, offset = 0)
        if mode != SYNCW_METADATA_TYPE_DIR:
            raise ObjectFormatError('corrupt dir object ' + dir_id)

        dirents = {}

        off = 4
        while True:
            fmt = "!i40si"
            mode, eid, name_len = struct.unpack_from(fmt, data, offset=off)
            off += struct.calcsize(fmt)

            fmt = "!%ds" % name_len
            name, = struct.unpack_from(fmt, data, offset = off)
            off += struct.calcsize(fmt)

            if stat.S_ISREG(mode):
                dirents[name] = SyncwDirent.fromV0(name, SyncwDirent.FILE, eid)
            elif stat.S_ISDIR(mode):
                dirents[name] = SyncwDirent.fromV0(name, SyncwDirent.DIR, eid)
            else:
                logger.warning('Error: unknown object mode %s', mode)
            if off > len(data) - 48:
                break

        return dirents

    def parse_dirents_v1(self, data, dir_id, ret_unicode=False):
        '''json format'''
        d = json.loads(data)

        dirents = {}

        for entry in d['dirents']:
            name = entry['name']
            id = entry['id']
            mtime = entry['mtime']
            mode = entry['mode']
            if stat.S_ISREG(mode):
                type = SyncwDirent.FILE
                size = entry['size']
            elif stat.S_ISDIR(mode):
                type = SyncwDirent.DIR
                size = 0
            else:
                continue

            if not ret_unicode:
                name = to_utf8(name)
                id = to_utf8(id)

            dirents[name] = SyncwDirent.fromV1(name, type, id, mtime, size)

        return dirents

    def parse_blocks_v0(self, data, obj_id):
        '''binray format'''
        blocks = []

        fmt = '!iq'
        mode, size = struct.unpack_from(fmt, data, offset=0)
        if mode != SYNCW_METADATA_TYPE_FILE:
            raise ObjectFormatError('corrupt file object ' + obj_id)

        off = struct.calcsize(fmt)
        while True:
            fmt = "!20s"
            bid, = struct.unpack_from(fmt, data, offset = off)
            hexs = []
            for d in bid:
                x = binascii.b2a_hex(d)
                hexs.append(x)

            blk_id = ''.join(hexs)
            blocks.append(blk_id)

            off += struct.calcsize(fmt)
            if off > len(data) - 20:
                break

        return blocks, size

    def parse_blocks_v1(self, data, obj_id):
        ''''json format'''
        d = json.loads(data)

        blocks = [ to_utf8(id) for id in d['block_ids'] ]
        size = d['size']

        return blocks, size

    def dir_read_count(self):
        return self._dir_counter
    def file_read_count(self):
        return self._file_counter


fs_mgr = SyncwFSManager()
