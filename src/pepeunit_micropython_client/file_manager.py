import ujson as json
import os
import gc
from shutil import shutil as shutil

import utils

class FileManager:
    @staticmethod
    async def _ensure_dir(path, *, yield_every=32):
        if not path:
            return
        if path.startswith('/'):
            base = '/'
            rest = path[1:]
        else:
            base = ''
            rest = path
        parts = []
        idx = 0
        for p in rest.split('/'):
            idx += 1
            parts.append(p)
            cur = (base + '/'.join(parts)) if base else '/'.join(parts)
            try:
                os.mkdir(cur)
            except OSError:
                pass
            await utils.ayield(idx, every=yield_every, do_gc=False)

    @staticmethod
    async def read_json(file_path):
        with open(file_path, 'r') as f:
            return json.load(f)

    @staticmethod
    async def write_json(file_path, data, *, yield_every=32):
        dirpath = utils.dirname(file_path)
        await FileManager._ensure_dir(dirpath, yield_every=yield_every)
        with open(file_path, 'w') as f:
            json.dump(data, f)
        await utils.ayield(0, every=1, do_gc=True)

    @staticmethod
    async def file_exists(file_path):
        try:
            os.stat(file_path)
            return True
        except OSError:
            return False

    @staticmethod
    async def append_ndjson_with_limit(file_path, item, max_lines, *, yield_every=32):
        dirpath = utils.dirname(file_path)
        await FileManager._ensure_dir(dirpath, yield_every=yield_every)

        try:
            with open(file_path, 'a') as f:
                if isinstance(item, str):
                    f.write(item)
                else:
                    json.dump(item, f)
                f.write('\n')
        except Exception:
            pass

        await utils.ayield(0, every=1, do_gc=False)
        await FileManager.trim_ndjson(file_path, max_lines, yield_every=yield_every)

    @staticmethod
    async def iter_lines_bytes_cb(file_path, on_line, *, yield_every=32):
        try:
            with open(file_path, 'rb') as f:
                idx = 0
                for line in f:
                    idx += 1
                    line = line.strip()
                    if not line:
                        continue
                    await utils.maybe_await(on_line(line))
                    await utils.ayield(idx, every=yield_every, do_gc=False)
        except Exception:
            return

    @staticmethod
    async def trim_ndjson(file_path, max_lines, *, yield_every=32):
        if max_lines <= 0:
            return
        try:
            total = 0
            tail = [None] * max_lines
            ti = 0
            with open(file_path, 'r') as f:
                for line in f:
                    total += 1
                    tail[ti] = line
                    ti = (ti + 1) % max_lines
                    await utils.ayield(total, every=yield_every, do_gc=False)
            if total <= max_lines:
                return
            tmp_path = file_path + '.tmp'
            with open(tmp_path, 'w') as dst:
                idx = 0
                while idx < max_lines:
                    line = tail[(ti + idx) % max_lines]
                    if line is not None:
                        dst.write(line)
                    idx += 1
                    await utils.ayield(idx, every=yield_every, do_gc=False)
            try:
                shutil.move(tmp_path, file_path)
            except Exception:
                try:
                    os.rename(tmp_path, file_path)
                except Exception:
                    pass
            gc.collect()
        except Exception:
            pass

    @staticmethod
    async def extract_tar_gz(tgz_path, dest_root, *, copy_chunk=256, yield_every=16):
        import tarfile
        import deflate

        await FileManager._ensure_dir(dest_root, yield_every=yield_every)

        with open(tgz_path, 'rb') as tgz:
            tar_file = deflate.DeflateIO(tgz, deflate.AUTO, 9)
            unpack_tar = tarfile.TarFile(fileobj=tar_file)
            for idx, unpack_file in enumerate(unpack_tar, 1):
                if unpack_file.type == tarfile.DIRTYPE or '@PaxHeader' in unpack_file.name:
                    continue

                out_path = dest_root + '/' + unpack_file.name[2:]
                out_dir = utils.dirname(out_path)
                await FileManager._ensure_dir(out_dir, yield_every=yield_every)
                subf = unpack_tar.extractfile(unpack_file)

                try:
                    with open(out_path, 'wb') as outf:
                        shutil.copyfileobj(subf, outf, length=copy_chunk)
                finally:
                    try:
                        if subf:
                            subf.close()
                    except Exception:
                        pass

                await utils.ayield(idx, every=yield_every, do_gc=True)

        gc.collect()
