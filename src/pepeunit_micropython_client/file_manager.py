import ujson as json
import os
import gc
from shutil import shutil as shutil


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
            return json.load(f)

    @staticmethod
    def write_json(file_path, data):
        FileManager._ensure_dir(FileManager.dirname(file_path))
        with open(file_path, 'w') as f:
            json.dump(data, f)
        gc.collect()

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
                        for it in data:
                            json.dump(it, fw)
                            fw.write('\n')
        except Exception:
            pass
        try:
            with open(file_path, 'a') as f:
                json.dump(item, f)
                f.write('\n')
        except Exception:
            pass
        gc.collect()
        FileManager.trim_ndjson(file_path, max_lines)

    @staticmethod
    def iter_ndjson(file_path):
        try:
            with open(file_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        yield json.loads(line)
                    except Exception:
                        continue
        except Exception:
            return

    @staticmethod
    def iter_lines_bytes(file_path):
        try:
            with open(file_path, 'rb') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        yield line
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
            with open(file_path, 'r') as f:
                for _ in f:
                    total += 1
            if total <= max_lines:
                return
            to_skip = total - max_lines
            tmp_path = file_path + '.tmp'
            with open(file_path, 'r') as src, open(tmp_path, 'w') as dst:
                for line in src:
                    if to_skip > 0:
                        to_skip -= 1
                        continue
                    dst.write(line)
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
            for unpack_file in unpack_tar:
                if unpack_file.type == tarfile.DIRTYPE or '@PaxHeader' in unpack_file.name:
                    continue
                
                out_path = dest_root + '/' + unpack_file.name[2:]
                FileManager._ensure_dir(FileManager.dirname(out_path))
                subf = unpack_tar.extractfile(unpack_file)

                with open(out_path, 'wb') as outf:
                    shutil.copyfileobj(subf, outf)
                    outf.close()
