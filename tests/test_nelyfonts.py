"""Офлайн-тесты NelyFonts. Запуск: python -m unittest discover -s tests -v"""
import os
import shutil
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sdk_stubs  # noqa: E402

nf = sdk_stubs.load_plugin_module()
ROOT = sdk_stubs.ROOT
FIX = os.path.join(ROOT, "tests", "fixtures")
TTF = os.path.join(ROOT, "First_Coffee_RU.ttf")
OTF = os.path.join(ROOT, "First_Coffee_RU.otf")


def read(path):
    with open(path, "rb") as f:
        return f.read()


class ParseFontTest(unittest.TestCase):
    def test_repo_fonts(self):
        for path, fmt in ((TTF, "TrueType"), (OTF, "OpenType (CFF)")):
            info = nf.parse_font(read(path), os.path.basename(path))
            self.assertEqual(info["family"], "First Coffee")
            self.assertEqual(info["format"], fmt)
            self.assertEqual(info["weight"], 400)
            self.assertFalse(info["italic"])
            self.assertTrue(info["cyrillic"])
            self.assertTrue(info["latin"])
            self.assertTrue(info["digits"])
            self.assertEqual(info["glyphs"], 185)
            self.assertFalse(info["variable"])

    def test_variable_font_axes_and_format12_cmap(self):
        info = nf.parse_font(read(os.path.join(FIX, "variable_wght.ttf")), "variable_wght.ttf")
        self.assertTrue(info["variable"])
        self.assertEqual(info["axes"]["wght"], [100.0, 400.0, 900.0])
        self.assertTrue(info["cyrillic"])
        self.assertEqual(info["family"], "Nely Var")

    def test_latin_only_bold_italic(self):
        info = nf.parse_font(read(os.path.join(FIX, "latin_bold_italic.ttf")), "x.ttf")
        self.assertEqual(info["weight"], 700)
        self.assertTrue(info["italic"])
        self.assertTrue(info["latin"])
        self.assertFalse(info["cyrillic"])

    def test_collection(self):
        info = nf.parse_font(read(os.path.join(FIX, "collection.ttc")), "c.ttc")
        self.assertTrue(info["collection"])
        self.assertEqual(info["family"], "Coll A")

    def test_truncated_and_garbage(self):
        data = read(TTF)
        with self.assertRaises(nf.FontParseError):
            nf.parse_font(data[: len(data) // 2], "half.ttf")
        with self.assertRaises(nf.FontParseError):
            nf.parse_font(b"\x00" * 4096, "zeros.ttf")  # то, что сохраняла старая версия
        with self.assertRaises(nf.FontParseError):
            nf.parse_font(b"abc", "tiny.ttf")

    def test_sniff(self):
        self.assertEqual(nf.sniff_kind(read(TTF)[:8]), "font")
        self.assertEqual(nf.sniff_kind(read(OTF)[:8]), "font")
        self.assertEqual(nf.sniff_kind(b"ttcf\x00\x01\x00\x00"), "font")
        self.assertEqual(nf.sniff_kind(b"wOF2abcd"), "woff")
        self.assertEqual(nf.sniff_kind(b"PK\x03\x04abcd"), "zip")
        self.assertEqual(nf.sniff_kind(b"<!DOCTYP"), "html")
        self.assertEqual(nf.sniff_kind(b"\x00\x00\x00\x00"), "unknown")


class ClassifyTest(unittest.TestCase):
    def test_assets(self):
        cases = {
            "fonts/rregular.ttf": "regular",
            "fonts/rmedium.ttf": "medium",
            "fonts/ritalic.ttf": "italic",
            "fonts/rmediumitalic.ttf": "medium_italic",
            "fonts/rcondensedbold.ttf": "bold",
            "fonts/rextrabold.ttf": "bold",
            "fonts/nunito_extrabold.ttf": "bold",
            "fonts/rmono.ttf": "mono",
            "fonts/mw_bold.ttf": "serif_bold",
            "fonts/mw_bolditalic.ttf": "serif_bold_italic",
            "fonts/num.otf": "special",
            "fonts/impact.ttf": "special",
            "fonts/NotoColorEmoji.ttf": "special",
        }
        for path, role in cases.items():
            self.assertEqual(nf.classify_asset(path), role, path)

    def test_families(self):
        self.assertEqual(nf.classify_family(None), "sans")
        self.assertEqual(nf.classify_family("sans-serif"), "sans")
        self.assertEqual(nf.classify_family("sans-serif-medium"), "sans-medium")
        self.assertEqual(nf.classify_family("sans-serif-black"), "sans-bold")
        self.assertEqual(nf.classify_family("serif-monospace"), "mono")
        self.assertEqual(nf.classify_family("serif"), "serif")
        self.assertIsNone(nf.classify_family("cursive"))
        self.assertIsNone(nf.classify_family("emoji"))
        self.assertEqual(nf.family_role("sans-medium", 0), "medium")
        self.assertEqual(nf.family_role("sans-medium", 2), "medium_italic")
        self.assertEqual(nf.family_role("sans", 3), "bold_italic")
        self.assertEqual(nf.family_role("serif", 1), "serif_bold")

    def test_weights_and_restyle(self):
        self.assertEqual(nf.role_for_weight(400, False), "regular")
        self.assertEqual(nf.role_for_weight(500, False), "medium")
        self.assertEqual(nf.role_for_weight(700, True), "bold_italic")
        self.assertEqual(nf.restyle("medium", 0), "medium")
        self.assertEqual(nf.restyle("medium", 1), "bold")
        self.assertEqual(nf.restyle("regular", 2), "italic")
        self.assertEqual(nf.restyle("special", 1), "special")
        self.assertEqual(nf.restyle("serif_regular", 1), "serif_bold")
        self.assertEqual(nf.restyle("bold", 2), "bold_italic")   # create(bold, ITALIC)
        self.assertEqual(nf.restyle("bold", 0), "bold")
        self.assertEqual(nf.restyle("bold_italic", 0), "bold")
        self.assertEqual(nf.restyle("italic", 0), "regular")
        self.assertEqual(nf.restyle("medium_italic", 2), "medium_italic")

    def test_guess_from_name(self):
        self.assertEqual(nf.guess_style_from_name("Inter-SemiBoldItalic.ttf"), (600, True))
        self.assertEqual(nf.guess_style_from_name("Roboto-Bold.ttf"), (700, False))
        self.assertEqual(nf.guess_style_from_name("Foo.ttf"), (400, False))


def cand(name, weight, italic=False, variable=False):
    return {"name": name, "path": name, "info": {"weight": weight, "italic": italic, "variable": variable}}


class AssignFamilyTest(unittest.TestCase):
    def test_static_family(self):
        cands = [cand("Inter-Regular.ttf", 400), cand("Inter-Bold.ttf", 700), cand("Inter-Medium.ttf", 500),
                 cand("Inter-Italic.ttf", 400, True), cand("Inter-BoldItalic.ttf", 700, True),
                 cand("Inter-Light.ttf", 300), cand("Inter_24pt-Regular.ttf", 400)]
        slots = nf.assign_family(cands)
        self.assertEqual(slots["regular"]["name"], "Inter-Regular.ttf")
        self.assertEqual(slots["bold"]["name"], "Inter-Bold.ttf")
        self.assertEqual(slots["medium"]["name"], "Inter-Medium.ttf")
        self.assertEqual(slots["italic"]["name"], "Inter-Italic.ttf")
        self.assertEqual(slots["bold_italic"]["name"], "Inter-BoldItalic.ttf")
        self.assertNotIn("medium_italic", slots)

    def test_variable_only(self):
        slots = nf.assign_family([cand("Foo[wght].ttf", 400, variable=True),
                                  cand("Foo-Italic[wght].ttf", 400, True, variable=True)])
        self.assertEqual(slots["regular"]["name"], "Foo[wght].ttf")
        self.assertEqual(slots["italic"]["name"], "Foo-Italic[wght].ttf")

    def test_semibold_not_reused(self):
        slots = nf.assign_family([cand("A-Regular.ttf", 400), cand("A-SemiBold.ttf", 600)])
        self.assertEqual(slots["bold"]["name"], "A-SemiBold.ttf")
        self.assertNotIn("medium", slots)

    def test_no_regular_weight(self):
        slots = nf.assign_family([cand("A-Black.ttf", 900), cand("A-Light.ttf", 300, True)])
        self.assertEqual(list(slots), ["regular"])


class UrlTest(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(nf.normalize_source("https://github.com/NeLydim/First-Coffee-RU/blob/main/First_Coffee_RU.ttf"),
                         ("url", "https://raw.githubusercontent.com/NeLydim/First-Coffee-RU/main/First_Coffee_RU.ttf"))
        self.assertEqual(nf.normalize_source("drive.google.com/file/d/AbC123/view?usp=sharing"),
                         ("url", "https://drive.google.com/uc?export=download&id=AbC123"))
        self.assertEqual(nf.normalize_source("https://www.dropbox.com/s/x/f.ttf?dl=0"),
                         ("url", "https://www.dropbox.com/s/x/f.ttf?dl=1"))
        self.assertEqual(nf.normalize_source("  /sdcard/Download/a.ttf "), ("path", "/sdcard/Download/a.ttf"))
        self.assertEqual(nf.normalize_source("file:///sdcard/a%20b.ttf"), ("path", "/sdcard/a b.ttf"))
        self.assertEqual(nf.normalize_source(""), (None, None))
        self.assertEqual(nf.name_from_url("https://x.org/f/My%20Font.otf?x=1"), "My Font.otf")
        self.assertEqual(nf.safe_name("../../etc/pa ss?.ttf"), "pa ss_.ttf")


class PluginTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="nelyfonts-test-")
        self.old_cwd = os.getcwd()
        os.chdir(self.tmp)
        sdk_stubs.BulletinHelper.shown.clear()
        self.plugin = nf.NelyFontsPlugin()
        self.plugin.on_plugin_load()

    def tearDown(self):
        try:
            self.plugin.on_plugin_unload()
        finally:
            os.chdir(self.old_cwd)
            shutil.rmtree(self.tmp, ignore_errors=True)

    def toasts(self, kind):
        return [m for k, m in sdk_stubs.BulletinHelper.shown if k == kind]


class ImportPipelineTest(PluginTestBase):
    def test_import_single_file(self):
        ok = self.plugin._import([("path", TTF)], None, "file")
        self.assertTrue(ok, self.plugin._report())
        meta = self.plugin.store.meta
        self.assertEqual(meta["family"], "First Coffee")
        self.assertEqual(set(meta["slots"]), {"regular"})
        stored = self.plugin.store.path(meta["slots"]["regular"]["file"])
        self.assertEqual(read(stored), read(TTF))
        fs = self.plugin.core.fs
        self.assertIsNotNone(fs)
        self.assertEqual(fs.roles["regular"].weight, 400)
        self.assertEqual(fs.roles["bold"].synth, nf.BOLD)            # синтетический жирный
        self.assertIs(fs.roles["medium"], fs.roles["bold"])          # medium_as_bold по умолчанию
        self.assertTrue(self.plugin.settings.get("enabled"))
        self.assertIn("«First Coffee» применён", self.toasts("success"))
        # Повторная загрузка с диска (как при перезапуске приложения)
        store = nf.FontStore(self.plugin.store.root)
        self.assertEqual(store.load()["family"], "First Coffee")

    def test_import_zip_family_with_junk(self):
        zpath = os.path.join(self.tmp, "family.zip")
        with zipfile.ZipFile(zpath, "w") as z:
            z.write(TTF, "First Coffee/static/FirstCoffee-Regular.ttf")
            z.write(os.path.join(FIX, "latin_bold_italic.ttf"), "First Coffee/static/FirstCoffee-BoldItalic.ttf")
            z.writestr("__MACOSX/._FirstCoffee-Regular.ttf", b"junk")
            z.writestr("OFL.txt", "license")
        self.assertTrue(self.plugin._import([("path", zpath)], None, "file"))
        slots = self.plugin.store.meta["slots"]
        self.assertEqual(set(slots), {"regular", "bold_italic"})
        fs = self.plugin.core.fs
        self.assertIn("bold_italic", fs.real)
        self.assertEqual(fs.roles["bold_italic"].weight, 700)

    def test_multiple_sources_with_same_names(self):
        paths = []
        for i, src in enumerate((TTF, os.path.join(FIX, "latin_bold_italic.ttf"))):
            zpath = os.path.join(self.tmp, "pack%d" % i, "font.zip")
            os.makedirs(os.path.dirname(zpath))
            with zipfile.ZipFile(zpath, "w") as z:
                z.write(src, "font.ttf")
            paths.append(("path", zpath))
        self.assertTrue(self.plugin._import(paths, None, "file"))
        self.assertEqual(set(self.plugin.store.meta["slots"]), {"regular", "bold_italic"})

    def test_slot_import_keeps_family(self):
        self.assertTrue(self.plugin._import([("path", TTF)], None, "file"))
        self.assertTrue(self.plugin._import([("path", os.path.join(FIX, "latin_bold_italic.ttf"))], "bold", "file"))
        self.assertEqual(set(self.plugin.store.meta["slots"]), {"regular", "bold"})
        self.assertTrue(self.plugin.store.remove_slot("bold"))
        self.assertEqual(set(self.plugin.store.meta["slots"]), {"regular"})
        # Файлы убранных начертаний удаляются
        files = sorted(os.listdir(self.plugin.store.root))
        self.assertEqual(len(files), 2, files)  # meta.json + regular

    def test_slot_requires_main_font(self):
        self.assertFalse(self.plugin._import([("path", TTF)], "bold", "file"))
        self.assertIn("Сначала выберите основной шрифт", self.toasts("error"))

    def test_variable_font_uses_axes(self):
        self.assertTrue(self.plugin._import([("path", os.path.join(FIX, "variable_wght.ttf"))], None, "file"))
        fs = self.plugin.core.fs
        self.assertEqual(fs.roles["regular"].variation, "'wght' 400")
        self.assertEqual(fs.roles["medium"].variation, "'wght' 500")
        self.assertEqual(fs.roles["bold"].variation, "'wght' 700")
        self.assertIsNone(fs.roles["bold"].synth)
        self.assertIn("medium", fs.real)

    def test_rejects_bad_files(self):
        woff = os.path.join(self.tmp, "web.woff2")
        with open(woff, "wb") as f:
            f.write(b"wOF2" + b"\x00" * 100)
        self.assertFalse(self.plugin._import([("path", woff)], None, "file"))
        self.assertTrue(any("WOFF" in m for m in self.toasts("error")))

        zeros = os.path.join(self.tmp, "zeros.ttf")
        with open(zeros, "wb") as f:
            f.write(b"\x00\x01\x00\x00" + b"\x00" * 200)
        self.assertFalse(self.plugin._import([("path", zeros)], None, "file"))
        self.assertTrue(any("повреждён" in m for m in self.toasts("error")))

        html = os.path.join(self.tmp, "page.ttf")
        with open(html, "wb") as f:
            f.write(b"<!DOCTYPE html><html></html>")
        self.assertFalse(self.plugin._import([("path", html)], None, "file"))
        self.assertTrue(any("веб-страница" in m for m in self.toasts("error")))
        self.assertIsNone(self.plugin.store.meta)  # рабочий шрифт ничем не испорчен

    def test_failed_import_keeps_previous_font(self):
        self.assertTrue(self.plugin._import([("path", TTF)], None, "file"))
        before = dict(self.plugin.store.meta)
        broken = os.path.join(self.tmp, "broken.ttf")
        with open(broken, "wb") as f:
            f.write(read(OTF)[:5000])
        self.assertFalse(self.plugin._import([("path", broken)], None, "file"))
        self.assertEqual(self.plugin.store.meta, before)

    def test_copy_stream_writes_real_bytes(self):
        data = read(TTF)
        stream = sdk_stubs.FakeInputStream(data)
        dst = os.path.join(self.tmp, "copy.ttf")
        self.assertEqual(self.plugin._copy_stream(stream, dst), len(data))
        self.assertEqual(read(dst), data)
        self.assertTrue(stream.closed)
        with self.assertRaises(nf.ImportFailure):
            self.plugin._copy_stream(sdk_stubs.FakeInputStream(b""), os.path.join(self.tmp, "empty.ttf"))

    def test_reset(self):
        self.assertTrue(self.plugin._import([("path", TTF)], None, "file"))
        self.plugin.store.clear()
        self.plugin._deactivate("x")
        self.assertIsNone(self.plugin.core.fs)
        self.assertEqual(os.listdir(self.plugin.store.root), [])


class FakeParam:
    def __init__(self, *args, this=None):
        self.args = list(args)
        self.thisObject = this
        self.result = "unset"

    def setResult(self, value):
        self.result = value


class HookLogicTest(PluginTestBase):
    def setUp(self):
        super().setUp()
        self.assertTrue(self.plugin._import([("path", TTF)], None, "file"))
        self.fs = self.plugin.core.fs
        self.core = self.plugin.core

    def test_provider_hook(self):
        hook = nf._ProviderHook(self.plugin)
        for path, role in (("fonts/rregular.ttf", "regular"), ("fonts/rmedium.ttf", "medium"),
                           ("fonts/ritalic.ttf", "italic")):
            p = FakeParam(path)
            hook.before_hooked_method(p)
            self.assertIs(p.result, self.fs.roles[role])
        for path in ("fonts/rmono.ttf", "fonts/num.otf", "fonts/mw_bold.ttf"):
            p = FakeParam(path)
            hook.before_hooked_method(p)
        # mono сохраняется по умолчанию, num — всегда, serif заменяется (keep_serif=False)
        p = FakeParam("fonts/rmono.ttf")
        hook.before_hooked_method(p)
        self.assertEqual(p.result, "unset")
        p = FakeParam("fonts/num.otf")
        hook.before_hooked_method(p)
        self.assertEqual(p.result, "unset")
        p = FakeParam("fonts/mw_bold.ttf")
        hook.before_hooked_method(p)
        self.assertIs(p.result, self.fs.roles["bold"])

    def test_factory_hooks_touch_only_system_faces(self):
        Tf = sdk_stubs.FakeTypefaceClass
        hook = nf._CreateByFamilyHook(self.plugin)
        p = FakeParam(Tf.DEFAULT, nf.BOLD)
        hook.before_hooked_method(p)
        self.assertIs(p.result, self.fs.roles["bold"])
        p = FakeParam(None, nf.ITALIC)
        hook.before_hooked_method(p)
        self.assertIs(p.result, self.fs.roles["italic"])
        emoji = sdk_stubs.FakeTypeface("emoji.ttf")
        p = FakeParam(emoji, nf.BOLD)
        hook.before_hooked_method(p)
        self.assertEqual(p.result, "unset")
        p = FakeParam(Tf.MONOSPACE, nf.BOLD)
        hook.before_hooked_method(p)
        self.assertEqual(p.result, "unset")

        by_name = nf._CreateByNameHook(self.plugin)
        p = FakeParam("sans-serif-medium", 0)
        by_name.before_hooked_method(p)
        self.assertIs(p.result, self.fs.roles["medium"])
        p = FakeParam("cursive", 0)
        by_name.before_hooked_method(p)
        self.assertEqual(p.result, "unset")

        weight = nf._CreateWeightHook(self.plugin)
        p = FakeParam(Tf.SANS_SERIF, 500, False)
        weight.before_hooked_method(p)
        self.assertIs(p.result, self.fs.roles["medium"])

    def test_guard_and_stale_instance(self):
        hook = nf._ProviderHook(self.plugin)
        with nf._Guard():
            with nf._Guard():
                pass
            p = FakeParam("fonts/rregular.ttf")
            hook.before_hooked_method(p)
            self.assertEqual(p.result, "unset")   # внешний guard ещё активен
        setattr(sys, nf.OWNER_ATTR, object())       # плагин переустановлен — старые хуки молчат
        p = FakeParam("fonts/rregular.ttf")
        hook.before_hooked_method(p)
        self.assertEqual(p.result, "unset")
        setattr(sys, nf.OWNER_ATTR, self.plugin._token)

    def test_ctor_and_arg_hooks(self):
        class View:
            def __init__(self, tf):
                self.tf = tf

            def getTypeface(self):
                return self.tf

            def setTypeface(self, tf):
                self.tf = tf
        v = View(None)
        nf._TextViewCtorHook(self.plugin).after_hooked_method(FakeParam(this=v))
        self.assertIs(v.tf, self.fs.roles["regular"])
        mono = View(sdk_stubs.FakeTypefaceClass.MONOSPACE)
        nf._TextViewCtorHook(self.plugin).after_hooked_method(FakeParam(this=mono))
        self.assertIs(mono.tf, sdk_stubs.FakeTypefaceClass.MONOSPACE)
        p = FakeParam("text", 14.0, None)
        nf._TypefaceArgHook(self.plugin, 2).before_hooked_method(p)
        self.assertIs(p.args[2], self.fs.roles["regular"])

    def test_activity_result_hook(self):
        picked = []
        self.plugin.on_files_picked = lambda uris, slot: picked.append((uris, slot))

        class Intent:
            def getClipData(self):
                return None

            def getData(self):
                return "content://x/font.ttf"
        hook = nf._ActivityResultHook(self.plugin)
        hook.before_hooked_method(FakeParam(nf.REQ_BASE + 3, -1, Intent()))
        hook.before_hooked_method(FakeParam(nf.REQ_BASE, 0, Intent()))       # отмена
        hook.before_hooked_method(FakeParam(1234, -1, Intent()))              # чужой код
        self.assertEqual(picked, [(["content://x/font.ttf"], "bold")])

    def test_pick_dedupe(self):
        calls = []
        self.plugin.import_async = lambda sources, **kw: calls.append(sources)
        self.plugin.on_files_picked(["u1"], None)
        self.plugin.on_files_picked(["u1"], None)
        self.assertEqual(len(calls), 1)

    def test_paint_patcher_roundtrip(self):
        class Paint:
            def __init__(self, tf):
                self.tf = tf

            def getTypeface(self):
                return self.tf

            def setTypeface(self, tf):
                self.tf = tf
        Tf = sdk_stubs.FakeTypefaceClass
        custom = sdk_stubs.FakeTypeface("custom")
        paints = [Paint(None), Paint(Tf.DEFAULT_BOLD), Paint(Tf.MONOSPACE), Paint(custom)]
        patcher = self.plugin.patcher
        patcher._paints = lambda: iter(paints)
        patcher.apply(self.core, self.fs)
        self.assertIs(paints[0].tf, self.fs.roles["regular"])
        self.assertIs(paints[1].tf, self.fs.roles["bold"])
        self.assertIs(paints[2].tf, Tf.MONOSPACE)
        self.assertIs(paints[3].tf, custom)
        self.core.set_fontset(None)
        patcher.restore(self.core)
        self.assertIsNone(paints[0].tf)
        self.assertIs(paints[1].tf, Tf.DEFAULT_BOLD)


class SettingsTest(PluginTestBase):
    def test_settings_pages_build(self):
        items = self.plugin.create_settings()
        texts = [getattr(i, "text", "") for i in items]
        self.assertIn("NelyFonts", texts)
        self.assertIn("Выбрать файлы шрифта", texts)
        self.assertIn("Шрифт не выбран", texts)
        self.assertFalse(any(i.kind == "Text" and "Ошибка" in i.text for i in items))
        self.assertTrue(self.plugin._import([("path", TTF)], None, "file"))
        texts = [getattr(i, "text", "") for i in self.plugin.create_settings()]
        self.assertIn("First Coffee — активен", texts)
        for page in (self.plugin._page_inspector, self.plugin._page_slots, self.plugin._page_downloads):
            self.assertTrue(page())
        report = self.plugin._report()
        self.assertIn("First Coffee", report)

    def test_icons_exist_in_app(self):
        # Имена иконок, проверенные по R.drawable в exteraGram/AyuGram 12.x
        valid = {"msg_photo_text_regular", "msg_photo_text_framed3", "msg_openin", "msg_download", "msg_link",
                 "msg_fave", "msg_list", "msg_photo_text2", "msg_text_outlined", "msg_photo_text_framed",
                 "msg_customize", "msg_stats", "msg_retry", "msg_reset", "msg_delete", "msg_search",
                 "msg_copy", "msg_info"}
        self.assertTrue(self.plugin._import([("path", TTF)], None, "file"))
        items = list(self.plugin.create_settings())
        for page in (self.plugin._page_inspector, self.plugin._page_slots, self.plugin._page_downloads):
            items += page()
        for item in items:
            icon = getattr(item, "icon", None)
            if icon:
                self.assertIn(icon, valid)


class TelegramCacheTest(unittest.TestCase):
    """Кеш Telegram + уже показанные вью, когда хуки на regular()/bold() не срабатывают."""

    def setUp(self):
        stubs = sdk_stubs
        stubs.FakeAU.reset()
        self.orig_regular = stubs.FakeAU.regular()
        self.orig_medium = stubs.FakeAU.bold()
        self.header = stubs.FakeTextView(self.orig_medium)          # HeaderCell: bold()
        self.cell = stubs.FakeTextView(self.orig_regular)           # TextCell: regular()
        self.plain = stubs.FakeTextView(None)
        self.mono = stubs.FakeTextView(stubs.FakeTypefaceClass.MONOSPACE)
        root = stubs.FakeViewGroup(self.header, stubs.FakeViewGroup(self.cell, self.plain, self.mono))
        stubs.FakeLaunchActivity.instance = stubs.FakeLaunchActivity(root)
        stubs.JCLASSES.update({
            nf.AU_CLASS: stubs.FakeAU,
            "android.widget.TextView": stubs.FakeTextView,
            "android.view.ViewGroup": stubs.FakeViewGroup,
            "org.telegram.ui.LaunchActivity": stubs.FakeLaunchActivity,
        })
        nf.J._cache[nf.AU_CLASS] = stubs.FakeAUClass()
        self.tmp = tempfile.mkdtemp(prefix="nelyfonts-cache-")
        self.old_cwd = os.getcwd()
        os.chdir(self.tmp)
        self.plugin = nf.NelyFontsPlugin()
        self.plugin.on_plugin_load()

    def tearDown(self):
        self.plugin.on_plugin_unload()
        for k in (nf.AU_CLASS, "android.widget.TextView", "android.view.ViewGroup",
                  "org.telegram.ui.LaunchActivity"):
            sdk_stubs.JCLASSES.pop(k, None)
        nf.J._cache.pop(nf.AU_CLASS, None)
        os.chdir(self.old_cwd)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_cache_primed_and_views_patched(self):
        AU = sdk_stubs.FakeAU
        self.assertTrue(self.plugin._import([("path", TTF)], None, "file"))
        fs = self.plugin.core.fs
        self.assertIs(AU.regular(), fs.roles["regular"])
        self.assertIs(AU.bold(), fs.roles["medium"])
        self.assertIs(AU.getTypeface("fonts/ritalic.ttf"), fs.roles["italic"])
        self.assertIs(AU.getTypeface("fonts/rcondensedbold.ttf"), fs.roles["bold"])
        self.assertIsNot(AU.getTypeface("fonts/rmono.ttf"), fs.roles["regular"])  # моно оставлен
        self.assertIs(self.header.tf, fs.roles["medium"])
        self.assertIs(self.cell.tf, fs.roles["regular"])
        self.assertIs(self.plain.tf, fs.roles["regular"])
        self.assertIs(self.mono.tf, sdk_stubs.FakeTypefaceClass.MONOSPACE)
        self.assertGreaterEqual(self.plugin.primed, 7)
        self.assertEqual(self.plugin._tree_snapshot()[:2], (3, 3))

    def test_reprime_after_external_clear(self):
        AU = sdk_stubs.FakeAU
        self.assertTrue(self.plugin._import([("path", TTF)], None, "file"))
        fs = self.plugin.core.fs
        AU.clearTypefaceCache()                     # например, exteraGram «Системный шрифт»
        nf._ClearCacheHook(self.plugin).after_hooked_method(object())
        self.assertIs(AU.regular(), fs.roles["regular"])
        self.assertIs(AU.bold(), fs.roles["medium"])

    def test_disable_restores_originals(self):
        AU = sdk_stubs.FakeAU
        self.assertTrue(self.plugin._import([("path", TTF)], None, "file"))
        self.plugin._deactivate()
        core = self.plugin.core
        for tf in (AU.regular(), AU.bold(), self.header.tf, self.cell.tf, self.plain.tf):
            self.assertFalse(core.is_ours(tf), tf)
        self.assertEqual(core.classify(self.header.tf), "medium")

    def test_switching_fonts_replaces_previous(self):
        AU = sdk_stubs.FakeAU
        self.assertTrue(self.plugin._import([("path", TTF)], None, "file"))
        self.assertTrue(self.plugin._import([("path", os.path.join(FIX, "variable_wght.ttf"))], None, "file"))
        fs = self.plugin.core.fs
        self.assertIn("variable_wght", str(fs.roles["regular"].src) + self.plugin.store.meta["slots"]["regular"]["name"])
        self.assertIs(AU.regular(), fs.roles["regular"])
        self.assertIs(self.cell.tf, fs.roles["regular"])
        self.assertIs(self.header.tf, fs.roles["medium"])


class MetadataTest(unittest.TestCase):
    def test_metadata(self):
        self.assertEqual(nf.__name__, "NelyFonts")
        self.assertEqual(nf.__id__, "nelyfonts")
        self.assertRegex(nf.__version__, r"^\d+\.\d+\.\d+$")


if __name__ == "__main__":
    unittest.main()
