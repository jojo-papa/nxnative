import hashlib
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
from webui.packages import decompress_nsz, entries, xci_entries, repack


def container(magic, files):
    names, table, payload = bytearray(), bytearray(), bytearray()
    for name, content in files:
        if magic == b'PFS0':
            table.extend(struct.pack('<QQII', len(payload), len(content), len(names), 0))
        else:
            table.extend(struct.pack('<QQIIQ', len(payload), len(content), len(names), len(content), 0))
            table.extend(hashlib.sha256(content).digest())
        names.extend(name.encode() + b'\0'); payload.extend(content)
    return struct.pack('<4sIII', magic, len(files), len(names), 0) + table + names + payload


class Containers(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def file(self, content):
        path = self.root / 'input.bin'; path.write_bytes(content); return path

    def test_stream_roundtrip(self):
        path = self.file(container(b'PFS0', [('a.nca', b'a' * 30000), ('b.nca', b'b')]))
        output = self.root / 'output.nsp'
        repack(path, entries(path), output)
        for item in entries(output):
            with output.open('rb') as stream:
                stream.seek(item.offset)
                self.assertEqual(stream.read(item.size), b'a' * 30000 if item.name == 'a.nca' else b'b')

    def test_unsafe_names(self):
        for name in ('../outside', 'a\\b', 'C:evil', '..'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                entries(self.file(container(b'PFS0', [(name, b'x')])))

    def test_duplicate_names(self):
        with self.assertRaises(ValueError):
            entries(self.file(container(b'PFS0', [('a', b'1'), ('A', b'2')])))

    def test_truncated(self):
        with self.assertRaises(ValueError):
            entries(self.file(container(b'PFS0', [('a', b'1')])[:-1]))

    def test_xci_secure_and_hash(self):
        secure = container(b'HFS0', [('a.nca', b'abc')])
        root = container(b'HFS0', [('secure', secure)])
        header = bytearray(0x200); header[0x100:0x104] = b'HEAD'
        struct.pack_into('<Q', header, 0x130, len(header))
        path = self.file(header + root)
        self.assertEqual(xci_entries(path)[0].name, 'a.nca')
        damaged = bytearray(path.read_bytes()); damaged[-1] ^= 1; path.write_bytes(damaged)
        with self.assertRaises(ValueError): xci_entries(path)

    def test_no_partial_output_after_hash_failure(self):
        path = self.file(container(b'PFS0', [('a', b'x')]))
        out = self.root / 'out.nsp'
        with self.assertRaises(ValueError): repack(path, entries(path), out, hashes={'a':'00'})
        self.assertFalse(out.exists()); self.assertFalse(out.with_name('out.nsp.partial').exists())

    def test_nsz_decompression_command_and_output(self):
        source = self.root / 'update.nsz'; source.write_bytes(b'nsz')
        keys = self.root / 'prod.keys'; keys.write_bytes(b'keys')
        destination = self.root / 'nsz-out'
        commands = []
        def fake_run(folder, command):
            commands.append([str(x) for x in command])
            destination.mkdir(exist_ok=True)
            (destination / 'update.nsp').write_bytes(b'nsp')
        with patch('webui.packages.importlib.util.find_spec', return_value=object()):
            outputs = decompress_nsz(source, destination, keys, fake_run, self.root)
        self.assertEqual([path.name for path in outputs], ['update.nsp'])
        self.assertIn('-D', commands[0])
        self.assertIn('--minimal-output', commands[0])
        self.assertEqual(Path(commands[0][commands[0].index('--keys') + 1]), keys)
        self.assertEqual(Path(commands[0][commands[0].index('-o') + 1]), destination)

    def test_overlapping_entries(self):
        data = bytearray(container(b'PFS0', [('a', b'a'), ('b', b'b')]))
        struct.pack_into('<Q', data, 40, 0)
        with self.assertRaises(ValueError): entries(self.file(data))


if __name__ == '__main__': unittest.main()
