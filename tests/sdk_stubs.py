"""Минимальные заглушки SDK exteraGram и Chaquopy для офлайн-тестов плагина.

Настоящие Java-классы недоступны вне Android, поэтому здесь — простые
Python-подделки, достаточные, чтобы проверить логику импорта, разбора
шрифтов, ролей начертаний и хуков.
"""
import importlib.machinery
import importlib.util
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN_PATH = os.path.join(ROOT, "NelyFonts.plugin")


# ---- android.graphics.Typeface и друзья -----------------------------------
class FakeTypeface:
    def __init__(self, src, weight=400, italic=False, synth=None, variation=None):
        self.src = src
        self.weight = weight
        self.italic = italic
        self.synth = synth
        self.variation = variation

    def equals(self, other):
        return self is other

    def __repr__(self):
        return "TF(%s w%s%s%s%s)" % (os.path.basename(str(self.src)), self.weight,
                                     " i" if self.italic else "",
                                     " synth=%s" % self.synth if self.synth is not None else "",
                                     " var=%s" % self.variation if self.variation else "")


class FakeTypefaceClass:
    DEFAULT = FakeTypeface("DEFAULT")
    SANS_SERIF = FakeTypeface("SANS_SERIF")
    DEFAULT_BOLD = FakeTypeface("DEFAULT_BOLD", 700)
    MONOSPACE = FakeTypeface("MONOSPACE")
    SERIF = FakeTypeface("SERIF")
    _defaults = {}
    _named = {}

    @classmethod
    def create(cls, base, style):
        if isinstance(base, str):
            key = (base, style)
            if key not in cls._named:
                cls._named[key] = FakeTypeface("sys:" + base, 700 if style & 1 else 400, bool(style & 2))
            return cls._named[key]
        return FakeTypeface(base.src, base.weight, base.italic or bool(style & 2), synth=style,
                            variation=base.variation)

    @classmethod
    def defaultFromStyle(cls, style):
        if style not in cls._defaults:
            cls._defaults[style] = FakeTypeface("default%d" % style)
        return cls._defaults[style]

    @staticmethod
    def createFromFile(path):
        return FakeTypeface(path)


class FakeFile:
    def __init__(self, path):
        self.path = path


class FakeBuilder:
    built = []

    def __init__(self, file):
        self.path = file.path
        self.weight = 400
        self.italic = False
        self.variation = None

    def setWeight(self, w):
        self.weight = w
        return self

    def setItalic(self, i):
        self.italic = i
        return self

    def setFontVariationSettings(self, v):
        self.variation = v
        return self

    def build(self):
        if not os.path.isfile(self.path):
            return None
        tf = FakeTypeface(self.path, self.weight, self.italic, variation=self.variation)
        FakeBuilder.built.append(tf)
        return tf


class FakeOutputStream:
    def __init__(self, path):
        self.f = open(path, "wb")

    def write(self, buf, off, n):
        self.f.write(bytes(buf[off:off + n]))

    def close(self):
        self.f.close()


class FakeInputStream:
    """InputStream.read(byte[]) — заполняет переданный буфер на месте."""

    def __init__(self, data, chunk=7000):
        self.data = data
        self.pos = 0
        self.chunk = chunk
        self.closed = False

    def read(self, buf):
        if self.pos >= len(self.data):
            return -1
        n = min(self.chunk, len(buf), len(self.data) - self.pos)
        buf[0:n] = self.data[self.pos:self.pos + n]
        self.pos += n
        return n

    def close(self):
        self.closed = True


JCLASSES = {
    "android.graphics.Typeface": FakeTypefaceClass,
    "android.graphics.Typeface$Builder": FakeBuilder,
    "java.io.File": FakeFile,
    "java.io.FileOutputStream": FakeOutputStream,
    "android.os.Build$VERSION": types.SimpleNamespace(SDK_INT=34),
}


def jclass(name):
    if name in JCLASSES:
        return JCLASSES[name]
    raise Exception("ClassNotFoundException: " + name)


def jarray(_type):
    return lambda n: bytearray(n)


def dynamic_proxy(_iface):
    class _Proxy:
        def __init__(self, *a, **k):
            pass
    return _Proxy


class FakeClass:
    @staticmethod
    def forName(*_a):
        raise Exception("ClassNotFoundException")


# ---- SDK exteraGram --------------------------------------------------------
class BasePlugin:
    def __init__(self):
        self.settings = {}
        self.logs = []
        self.hooked = []

    def get_setting(self, key, default=None):
        return self.settings.get(key, default)

    def set_setting(self, key, value, reload_settings=False):
        self.settings[key] = value

    def log(self, msg):
        self.logs.append(str(msg))

    def hook_method(self, member, hook, priority=10):
        self.hooked.append((member, hook))
        return (member, hook)

    def unhook_method(self, unhook):
        pass


class MethodHook:
    pass


class _Item:
    def __init__(self, **kw):
        self.__dict__.update(kw)
        self.kind = type(self).__name__

    def __repr__(self):
        return "%s(%s)" % (self.kind, self.__dict__.get("text") or self.__dict__.get("key"))


def _item(name):
    return type(name, (_Item,), {})


class BulletinHelper:
    shown = []

    @classmethod
    def show_success(cls, msg):
        cls.shown.append(("success", msg))

    @classmethod
    def show_error(cls, msg):
        cls.shown.append(("error", msg))

    @classmethod
    def show_info(cls, msg):
        cls.shown.append(("info", msg))


def install():
    def mod(name, **attrs):
        m = types.ModuleType(name)
        m.__dict__.update(attrs)
        sys.modules[name] = m
        return m

    mod("base_plugin", BasePlugin=BasePlugin, MethodHook=MethodHook)
    mod("android_utils", run_on_ui_thread=lambda fn, *a, **k: fn(), copy_to_clipboard=lambda t: None)
    mod("java", jclass=jclass, jarray=jarray, jbyte="byte", dynamic_proxy=dynamic_proxy)
    mod("java.lang", Class=FakeClass)
    mod("org")
    mod("org.telegram")
    mod("org.telegram.messenger", ApplicationLoader=types.SimpleNamespace(applicationContext=None))
    mod("ui")
    mod("ui.settings", **{n: _item(n) for n in ("Header", "Divider", "Text", "Input", "Switch")})
    mod("ui.bulletin", BulletinHelper=BulletinHelper)
    mod("client_utils", get_last_fragment=lambda: None)


def load_plugin_module():
    install()
    loader = importlib.machinery.SourceFileLoader("nelyfonts_plugin", PLUGIN_PATH)
    spec = importlib.util.spec_from_loader("nelyfonts_plugin", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module
