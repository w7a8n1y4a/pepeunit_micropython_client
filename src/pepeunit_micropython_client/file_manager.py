import ujson as json
import os

try:
    import uzlib
except ImportError:
    uzlib = None


class FileManager:
    @staticmethod
    def _dirname(path):
        idx = path.rfind('/')
        return path[:idx] if idx > 0 else ''
    @staticmethod
    def read_json(file_path):
        with open(file_path, 'r') as f:
            return json.load(f)

    @staticmethod
    def write_json(file_path, data, indent=None):
        FileManager._ensure_dir(FileManager._dirname(file_path))
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
    def create_directory(directory_path):
        FileManager._ensure_dir(directory_path)

    @staticmethod
    def copy_file(source_path, destination_path):
        FileManager._ensure_dir(FileManager._dirname(destination_path))
        with open(source_path, 'rb') as s, open(destination_path, 'wb') as d:
            while True:
                b = s.read(256)
                if not b:
                    break
                d.write(b)

    @staticmethod
    def copy_directory_contents(source_path, destination_path):
        FileManager._ensure_dir(destination_path)
        for name in os.listdir(source_path):
            sp = source_path + '/' + name
            dp = destination_path + '/' + name
            try:
                st = os.stat(sp)
                is_dir = (st[0] & 0x4000) != 0 if isinstance(st, tuple) else False
            except OSError:
                is_dir = False
            if FileManager._is_dir(sp):
                FileManager.copy_directory_contents(sp, dp)
            else:
                FileManager.copy_file(sp, dp)

    @staticmethod
    def append_to_json_list(file_path, item):
        data = []
        if FileManager.file_exists(file_path):
            try:
                data = FileManager.read_json(file_path)
                if not isinstance(data, list):
                    data = []
            except Exception:
                data = []
        data.append(item)
        FileManager.write_json(file_path, data)

    @staticmethod
    def extract_tar_gz(archive_path, extract_path):
        FileManager.extract_pepeunit_archive(archive_path, extract_path)

    @staticmethod
    def extract_pepeunit_archive(file_path, extract_path):
        if uzlib is None:
            raise OSError('uzlib not available')
        FileManager._ensure_dir(extract_path)
        tar_tmp = (file_path.rsplit('/', 1)[0] or '/') + '/temp_update.tar'
        with open(file_path, 'rb') as fin, open(tar_tmp, 'wb') as fout:
            decomp = uzlib.DecompIO(fin, 15)
            while True:
                chunk = decomp.read(256)
                if not chunk:
                    break
                fout.write(chunk)
        try:
            FileManager._extract_tar(tar_tmp, extract_path)
        finally:
            try:
                os.remove(tar_tmp)
            except OSError:
                pass

    @staticmethod
    def _extract_tar(tar_path, dest_dir):
        with open(tar_path, 'rb') as f:
            while True:
                header = f.read(512)
                if not header or header == b'\0' * 512:
                    break
                name = header[0:100].split(b'\0', 1)[0].decode('utf-8')
                size_str = header[124:136].split(b'\0', 1)[0].strip()
                size = int(size_str, 8) if size_str else 0
                typeflag = header[156:157]
                if typeflag == b'5':
                    FileManager._ensure_dir(dest_dir + '/' + name)
                else:
                    full_path = dest_dir + '/' + name
                    FileManager._ensure_dir(full_path.rsplit('/', 1)[0])
                    remaining = size
                    with open(full_path, 'wb') as out:
                        while remaining > 0:
                            to_read = 512 if remaining >= 512 else remaining
                            data = f.read(to_read)
                            if not data:
                                break
                            out.write(data)
                            remaining -= len(data)
                    pad = (512 - (size % 512)) % 512
                    if pad:
                        f.read(pad)

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
    def _is_dir(path):
        try:
            import stat
            return (os.stat(path)[0] & stat.S_IFDIR) == stat.S_IFDIR
        except Exception:
            try:
                os.listdir(path)
                return True
            except Exception:
                return False


