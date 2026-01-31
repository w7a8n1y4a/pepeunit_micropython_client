import ujson as json
import os
import gc
from shutil import shutil as shutil

import utils

class FileManager:
    @staticmethod
    def dirname(path):
        idx = path.rfind('/')
        return path[:idx] if idx > 0 else ''

    @staticmethod
    def _ensure_dir(path):
        if not path:
            return
        parts = []
        if path.startswith('/'):
            base = '/'
            rest = path[1:]
        else:
            base = ''
            rest = path
        for p in rest.split('/'):
            parts.append(p)
            cur = (base + '/'.join(parts)) if base else '/'.join(parts)
            try:
                os.mkdir(cur)
            except OSError:
                pass

    @staticmethod
    def read_json(file_path):
        with open(file_path, 'r') as f:
            data = json.load(f)
            if isinstance(data, str):
                data = json.loads(data)
            return data

    @staticmethod
    def write_json(file_path, data):
        FileManager._ensure_dir(FileManager.dirname(file_path))
        with open(file_path, 'w') as f:
            json.dump(data, f)

    @staticmethod
    def file_exists(file_path):
        try:
            os.stat(file_path)
            return True
        except OSError:
            return False

    @staticmethod
    def append_ndjson_with_limit(file_path, item, max_lines):
        FileManager._ensure_dir(FileManager.dirname(file_path))
        try:
            with open(file_path, 'r') as f:
                ch = ''
                while True:
                    c = f.read(1)
                    if not c or not c.isspace():
                        ch = c
                        break
            if ch == '[':
                data = FileManager.read_json(file_path)
                if isinstance(data, list):
                    with open(file_path, 'w') as fw:
                        for idx, it in enumerate(data, 1):
                            json.dump(it, fw)
                            fw.write('\n')
                            utils._yield(idx, every=32)
        except Exception:
            pass
        try:
            with open(file_path, 'a') as f:
                json.dump(item, f)
                f.write('\n')
        except Exception:
            pass
        FileManager.trim_ndjson(file_path, max_lines)

    @staticmethod
    def iter_ndjson(file_path):
        try:
            with open(file_path, 'r') as f:
                idx = 0
                for line in f:
                    idx += 1
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        yield json.loads(line)
                    except Exception:
                        continue
                    utils._yield(idx, every=32)
        except Exception:
            return

    @staticmethod
    def iter_lines_bytes(file_path):
        try:
            with open(file_path, 'rb') as f:
                idx = 0
                for line in f:
                    idx += 1
                    line = line.strip()
                    if line:
                        yield line
                    utils._yield(idx, every=32)
        except Exception:
            return

    @staticmethod
    def _move(src, dst):
        try:
            shutil.move(src, dst)
        except Exception:
            try:
                os.rename(src, dst)
            except Exception:
                pass

    @staticmethod
    def trim_ndjson(file_path, max_lines):
        if max_lines <= 0:
            return
        try:
            total = 0
            tail = []
            with open(file_path, 'r') as f:
                for line in f:
                    total += 1
                    if len(tail) < max_lines:
                        tail.append(line)
                    else:
                        tail.pop(0)
                        tail.append(line)
                    utils._yield(total, every=32)
            if total <= max_lines:
                return
            tmp_path = file_path + '.tmp'
            with open(tmp_path, 'w') as dst:
                for idx, line in enumerate(tail, 1):
                    dst.write(line)
                    utils._yield(idx, every=32)
            FileManager._move(tmp_path, file_path)
            gc.collect()
        except Exception:
            pass

    @staticmethod
    def extract_tar_gz(tgz_path, dest_root):
        import tarfile
        import deflate

        FileManager._ensure_dir(dest_root)

        with open(tgz_path, 'rb') as tgz:
            tar_file = deflate.DeflateIO(tgz, deflate.AUTO, 9)
            unpack_tar = tarfile.TarFile(fileobj=tar_file)
            for idx, unpack_file in enumerate(unpack_tar, 1):
                if unpack_file.type == tarfile.DIRTYPE or '@PaxHeader' in unpack_file.name:
                    continue
                
                out_path = dest_root + '/' + unpack_file.name[2:]
                FileManager._ensure_dir(FileManager.dirname(out_path))
                subf = unpack_tar.extractfile(unpack_file)

                try:
                    with open(out_path, 'wb') as outf:
                        shutil.copyfileobj(subf, outf, length=256)
                        outf.close()
                finally:
                    try:
                        if subf:
                            subf.close()
                    except Exception:
                        pass
                utils._yield(idx, every=32)
        gc.collect()
