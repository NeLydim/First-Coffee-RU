import os
import shutil
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sdk_stubs

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
            info = nf.inspect_font(read(path), os.path.basename(path))
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
        info = nf.inspect_font(read(os.path.join(FIX, "variable_wght.ttf")), "variable_wght.ttf")
        self.assertTrue(info["variable"])
        self.assertEqual(info["axes"]["wght"], [100.0, 400.0, 900.0])
        self.assertTrue(info["cyrillic"])
        self.assertEqual(info["family"], "Nely Var")

    def test_latin_only_bold_italic(self):
        info = nf.inspect_font(read(os.path.join(FIX, "latin_bold_italic.ttf")), "x.ttf")
        self.assertEqual(info["weight"], 700)
        self.assertTrue(info["italic"])
        self.assertTrue(info["latin"])
        self.assertFalse(info["cyrillic"])

    def test_collection(self):
        info = nf.inspect_font(read(os.path.join(FIX, "collection.ttc")), "c.ttc")
        self.assertTrue(info["collection"])
        self.assertEqual(info["family"], "Coll A")

    def test_truncated_and_garbage(self):
        data = read(TTF)
        with self.assertRaises(nf.BadFontFile):
            nf.inspect_font(data[: len(data) // 2], "half.ttf")
        with self.assertRaises(nf.BadFontFile):
            nf.inspect_font(b"\x00" * 4096, "zeros.ttf")
        with self.assertRaises(nf.BadFontFile):
            nf.inspect_font(b"abc", "tiny.ttf")

    def test_sniff(self):
        self.assertEqual(nf.detect_container(read(TTF)[:8]), "font")
        self.assertEqual(nf.detect_container(read(OTF)[:8]), "font")
        self.assertEqual(nf.detect_container(b"ttcf\x00\x01\x00\x00"), "font")
        self.assertEqual(nf.detect_container(b"wOF2abcd"), "woff")
        self.assertEqual(nf.detect_container(b"PK\x03\x04abcd"), "zip")
        self.assertEqual(nf.detect_container(b"<!DOCTYP"), "html")
        self.assertEqual(nf.detect_container(b"\x00\x00\x00\x00"), "unknown")


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
            self.assertEqual(nf.asset_face(path), role, path)

    def test_families(self):
        self.assertEqual(nf.family_type_of(None), "sans")
        self.assertEqual(nf.family_type_of("sans-serif"), "sans")
        self.assertEqual(nf.family_type_of("sans-serif-medium"), "sans-medium")
        self.assertEqual(nf.family_type_of("sans-serif-black"), "sans-bold")
        self.assertEqual(nf.family_type_of("serif-monospace"), "mono")
        self.assertEqual(nf.family_type_of("serif"), "serif")
        self.assertIsNone(nf.family_type_of("cursive"))
        self.assertIsNone(nf.family_type_of("emoji"))
        self.assertEqual(nf.face_for_family("sans-medium", 0), "medium")
        self.assertEqual(nf.face_for_family("sans-medium", 2), "medium_italic")
        self.assertEqual(nf.face_for_family("sans", 3), "bold_italic")
        self.assertEqual(nf.face_for_family("serif", 1), "serif_bold")

    def test_weights_and_restyle(self):
        self.assertEqual(nf.face_for_weight(400, False), "regular")
        self.assertEqual(nf.face_for_weight(500, False), "medium")
        self.assertEqual(nf.face_for_weight(700, True), "bold_italic")
        self.assertEqual(nf.derived_face("medium", 0), "medium")
        self.assertEqual(nf.derived_face("medium", 1), "bold")
        self.assertEqual(nf.derived_face("regular", 2), "italic")
        self.assertEqual(nf.derived_face("special", 1), "special")
        self.assertEqual(nf.derived_face("serif_regular", 1), "serif_bold")
        self.assertEqual(nf.derived_face("bold", 2), "bold_italic")
        self.assertEqual(nf.derived_face("bold", 0), "bold")
        self.assertEqual(nf.derived_face("bold_italic", 0), "bold")
        self.assertEqual(nf.derived_face("italic", 0), "regular")
        self.assertEqual(nf.derived_face("medium_italic", 2), "medium_italic")

    def test_guess_from_name(self):
        self.assertEqual(nf.style_from_filename("Inter-SemiBoldItalic.ttf"), (600, True))
        self.assertEqual(nf.style_from_filename("Roboto-Bold.ttf"), (700, False))
        self.assertEqual(nf.style_from_filename("Foo.ttf"), (400, False))


def cand(name, weight, italic=False, variable=False):
    return {"name": name, "path": name, "info": {"weight": weight, "italic": italic, "variable": variable}}


class AssignFamilyTest(unittest.TestCase):
    def test_static_family(self):
        cands = [cand("Inter-Regular.ttf", 400), cand("Inter-Bold.ttf", 700), cand("Inter-Medium.ttf", 500),
                 cand("Inter-Italic.ttf", 400, True), cand("Inter-BoldItalic.ttf", 700, True),
                 cand("Inter-Light.ttf", 300), cand("Inter_24pt-Regular.ttf", 400)]
        slots = nf.spread_family(cands)
        self.assertEqual(slots["regular"]["name"], "Inter-Regular.ttf")
        self.assertEqual(slots["bold"]["name"], "Inter-Bold.ttf")
        self.assertEqual(slots["medium"]["name"], "Inter-Medium.ttf")
        self.assertEqual(slots["italic"]["name"], "Inter-Italic.ttf")
        self.assertEqual(slots["bold_italic"]["name"], "Inter-BoldItalic.ttf")
        self.assertNotIn("medium_italic", slots)

    def test_variable_only(self):
        slots = nf.spread_family([cand("Foo[wght].ttf", 400, variable=True),
                                  cand("Foo-Italic[wght].ttf", 400, True, variable=True)])
        self.assertEqual(slots["regular"]["name"], "Foo[wght].ttf")
        self.assertEqual(slots["italic"]["name"], "Foo-Italic[wght].ttf")

    def test_semibold_not_reused(self):
        slots = nf.spread_family([cand("A-Regular.ttf", 400), cand("A-SemiBold.ttf", 600)])
        self.assertEqual(slots["bold"]["name"], "A-SemiBold.ttf")
        self.assertNotIn("medium", slots)

    def test_no_regular_weight(self):
        slots = nf.spread_family([cand("A-Black.ttf", 900), cand("A-Light.ttf", 300, True)])
        self.assertEqual(list(slots), ["regular"])


class UrlTest(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(nf.parse_link("https://github.com/NeLydim/First-Coffee-RU/blob/main/First_Coffee_RU.ttf"),
                         ("url", "https://raw.githubusercontent.com/NeLydim/First-Coffee-RU/main/First_Coffee_RU.ttf"))
        self.assertEqual(nf.parse_link("drive.google.com/file/d/AbC123/view?usp=sharing"),
                         ("url", "https://drive.google.com/uc?export=download&id=AbC123"))
        self.assertEqual(nf.parse_link("https://www.dropbox.com/s/x/f.ttf?dl=0"),
                         ("url", "https://www.dropbox.com/s/x/f.ttf?dl=1"))
        self.assertEqual(nf.parse_link("  /sdcard/Download/a.ttf "), ("path", "/sdcard/Download/a.ttf"))
        self.assertEqual(nf.parse_link("file:///sdcard/a%20b.ttf"), ("path", "/sdcard/a b.ttf"))
        self.assertEqual(nf.parse_link(""), (None, None))
        self.assertEqual(nf.link_filename("https://x.org/f/My%20Font.otf?x=1"), "My Font.otf")
        self.assertEqual(nf.clean_filename("../../etc/pa ss?.ttf"), "pa ss_.ttf")


class PluginTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="nelyfonts-test-")
        self.old_cwd = os.getcwd()
        os.chdir(self.tmp)
        sdk_stubs.BulletinHelper.shown.clear()
        self.owner = nf.NelyFonts()
        self.owner.on_plugin_load()

    def tearDown(self):
        try:
            self.owner.on_plugin_unload()
        finally:
            os.chdir(self.old_cwd)
            shutil.rmtree(self.tmp, ignore_errors=True)

    def toasts(self, kind):
        return [m for k, m in sdk_stubs.BulletinHelper.shown if k == kind]


class ImportPipelineTest(PluginTestBase):
    def test_import_single_file(self):
        ok = self.owner._intake([("path", TTF)], None, "file")
        self.assertTrue(ok, self.owner._diagnostics())
        meta = self.owner.vault.manifest
        self.assertEqual(meta["family"], "First Coffee")
        self.assertEqual(set(meta["slots"]), {"regular"})
        stored = self.owner.vault.file_at(meta["slots"]["regular"]["file"])
        self.assertEqual(read(stored), read(TTF))
        fs = self.owner.registry.kit
        self.assertIsNotNone(fs)
        self.assertEqual(fs.faces["regular"].weight, 400)
        self.assertEqual(fs.faces["bold"].synth, nf.ST_BOLD)
        self.assertIs(fs.faces["medium"], fs.faces["bold"])
        self.assertTrue(self.owner.settings.get("enabled"))
        self.assertIn("«First Coffee» применён", self.toasts("success"))
        store = nf.FontVault(self.owner.vault.folder)
        self.assertEqual(store.reload()["family"], "First Coffee")

    def test_import_zip_family_with_junk(self):
        zpath = os.path.join(self.tmp, "family.zip")
        with zipfile.ZipFile(zpath, "w") as z:
            z.write(TTF, "First Coffee/static/FirstCoffee-Regular.ttf")
            z.write(os.path.join(FIX, "latin_bold_italic.ttf"), "First Coffee/static/FirstCoffee-BoldItalic.ttf")
            z.writestr("__MACOSX/._FirstCoffee-Regular.ttf", b"junk")
            z.writestr("OFL.txt", "license")
        self.assertTrue(self.owner._intake([("path", zpath)], None, "file"))
        slots = self.owner.vault.manifest["slots"]
        self.assertEqual(set(slots), {"regular", "bold_italic"})
        fs = self.owner.registry.kit
        self.assertIn("bold_italic", fs.genuine)
        self.assertEqual(fs.faces["bold_italic"].weight, 700)

    def test_multiple_sources_with_same_names(self):
        paths = []
        for i, src in enumerate((TTF, os.path.join(FIX, "latin_bold_italic.ttf"))):
            zpath = os.path.join(self.tmp, "pack%d" % i, "font.zip")
            os.makedirs(os.path.dirname(zpath))
            with zipfile.ZipFile(zpath, "w") as z:
                z.write(src, "font.ttf")
            paths.append(("path", zpath))
        self.assertTrue(self.owner._intake(paths, None, "file"))
        self.assertEqual(set(self.owner.vault.manifest["slots"]), {"regular", "bold_italic"})

    def test_slot_import_keeps_family(self):
        self.assertTrue(self.owner._intake([("path", TTF)], None, "file"))
        self.assertTrue(self.owner._intake([("path", os.path.join(FIX, "latin_bold_italic.ttf"))], "bold", "file"))
        self.assertEqual(set(self.owner.vault.manifest["slots"]), {"regular", "bold"})
        self.assertTrue(self.owner.vault.drop_face("bold"))
        self.assertEqual(set(self.owner.vault.manifest["slots"]), {"regular"})
        files = sorted(os.listdir(self.owner.vault.folder))
        self.assertEqual(len(files), 2, files)

    def test_slot_requires_main_font(self):
        self.assertFalse(self.owner._intake([("path", TTF)], "bold", "file"))
        self.assertIn("Сначала выберите основной шрифт", self.toasts("error"))

    def test_variable_font_uses_axes(self):
        self.assertTrue(self.owner._intake([("path", os.path.join(FIX, "variable_wght.ttf"))], None, "file"))
        fs = self.owner.registry.kit
        self.assertEqual(fs.faces["regular"].variation, "'wght' 400")
        self.assertEqual(fs.faces["medium"].variation, "'wght' 500")
        self.assertEqual(fs.faces["bold"].variation, "'wght' 700")
        self.assertIsNone(fs.faces["bold"].synth)
        self.assertIn("medium", fs.genuine)

    def test_rejects_bad_files(self):
        woff = os.path.join(self.tmp, "web.woff2")
        with open(woff, "wb") as f:
            f.write(b"wOF2" + b"\x00" * 100)
        self.assertFalse(self.owner._intake([("path", woff)], None, "file"))
        self.assertTrue(any("WOFF" in m for m in self.toasts("error")))

        zeros = os.path.join(self.tmp, "zeros.ttf")
        with open(zeros, "wb") as f:
            f.write(b"\x00\x01\x00\x00" + b"\x00" * 200)
        self.assertFalse(self.owner._intake([("path", zeros)], None, "file"))
        self.assertTrue(any("повреждён" in m for m in self.toasts("error")))

        html = os.path.join(self.tmp, "page.ttf")
        with open(html, "wb") as f:
            f.write(b"<!DOCTYPE html><html></html>")
        self.assertFalse(self.owner._intake([("path", html)], None, "file"))
        self.assertTrue(any("веб-страница" in m for m in self.toasts("error")))
        self.assertIsNone(self.owner.vault.manifest)

    def test_failed_import_keeps_previous_font(self):
        self.assertTrue(self.owner._intake([("path", TTF)], None, "file"))
        before = dict(self.owner.vault.manifest)
        broken = os.path.join(self.tmp, "broken.ttf")
        with open(broken, "wb") as f:
            f.write(read(OTF)[:5000])
        self.assertFalse(self.owner._intake([("path", broken)], None, "file"))
        self.assertEqual(self.owner.vault.manifest, before)

    def test_copy_stream_writes_real_bytes(self):
        data = read(TTF)
        stream = sdk_stubs.FakeInputStream(data)
        dst = os.path.join(self.tmp, "copy.ttf")
        self.assertEqual(self.owner._drain_stream(stream, dst), len(data))
        self.assertEqual(read(dst), data)
        self.assertTrue(stream.closed)
        with self.assertRaises(nf.LoadError):
            self.owner._drain_stream(sdk_stubs.FakeInputStream(b""), os.path.join(self.tmp, "empty.ttf"))

    def test_reset(self):
        self.assertTrue(self.owner._intake([("path", TTF)], None, "file"))
        self.owner.vault.wipe()
        self.owner._disengage("x")
        self.assertIsNone(self.owner.registry.kit)
        self.assertEqual(os.listdir(self.owner.vault.folder), [])


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
        self.assertTrue(self.owner._intake([("path", TTF)], None, "file"))
        self.kit = self.owner.registry.kit
        self.registry = self.owner.registry

    def test_provider_hook(self):
        hook = nf._AssetLoaderHook(self.owner)
        for path, role in (("fonts/rregular.ttf", "regular"), ("fonts/rmedium.ttf", "medium"),
                           ("fonts/ritalic.ttf", "italic")):
            p = FakeParam(path)
            hook.before_hooked_method(p)
            self.assertIs(p.result, self.kit.faces[role])
        for path in ("fonts/rmono.ttf", "fonts/num.otf", "fonts/mw_bold.ttf"):
            p = FakeParam(path)
            hook.before_hooked_method(p)
        p = FakeParam("fonts/rmono.ttf")
        hook.before_hooked_method(p)
        self.assertEqual(p.result, "unset")
        p = FakeParam("fonts/num.otf")
        hook.before_hooked_method(p)
        self.assertEqual(p.result, "unset")
        p = FakeParam("fonts/mw_bold.ttf")
        hook.before_hooked_method(p)
        self.assertIs(p.result, self.kit.faces["bold"])

    def test_factory_hooks_touch_only_system_faces(self):
        Tf = sdk_stubs.FakeTypefaceClass
        hook = nf._DerivedFaceHook(self.owner)
        p = FakeParam(Tf.DEFAULT, nf.ST_BOLD)
        hook.before_hooked_method(p)
        self.assertIs(p.result, self.kit.faces["bold"])
        p = FakeParam(None, nf.ST_ITALIC)
        hook.before_hooked_method(p)
        self.assertIs(p.result, self.kit.faces["italic"])
        emoji = sdk_stubs.FakeTypeface("emoji.ttf")
        p = FakeParam(emoji, nf.ST_BOLD)
        hook.before_hooked_method(p)
        self.assertEqual(p.result, "unset")
        p = FakeParam(Tf.MONOSPACE, nf.ST_BOLD)
        hook.before_hooked_method(p)
        self.assertEqual(p.result, "unset")

        by_name = nf._FamilyNameHook(self.owner)
        p = FakeParam("sans-serif-medium", 0)
        by_name.before_hooked_method(p)
        self.assertIs(p.result, self.kit.faces["medium"])
        p = FakeParam("cursive", 0)
        by_name.before_hooked_method(p)
        self.assertEqual(p.result, "unset")

        weight = nf._WeightedFaceHook(self.owner)
        p = FakeParam(Tf.SANS_SERIF, 500, False)
        weight.before_hooked_method(p)
        self.assertIs(p.result, self.kit.faces["medium"])

    def test_guard_and_stale_instance(self):
        hook = nf._AssetLoaderHook(self.owner)
        with nf._Bypass():
            with nf._Bypass():
                pass
            p = FakeParam("fonts/rregular.ttf")
            hook.before_hooked_method(p)
            self.assertEqual(p.result, "unset")
        setattr(sys, nf.INSTANCE_SLOT, object())
        p = FakeParam("fonts/rregular.ttf")
        hook.before_hooked_method(p)
        self.assertEqual(p.result, "unset")
        setattr(sys, nf.INSTANCE_SLOT, self.owner._mark)

    def test_ctor_and_arg_hooks(self):
        class View:
            def __init__(self, tf):
                self.tf = tf

            def getTypeface(self):
                return self.tf

            def setTypeface(self, tf):
                self.tf = tf
        v = View(None)
        nf._TextViewInitHook(self.owner).after_hooked_method(FakeParam(this=v))
        self.assertIs(v.tf, self.kit.faces["regular"])
        mono = View(sdk_stubs.FakeTypefaceClass.MONOSPACE)
        nf._TextViewInitHook(self.owner).after_hooked_method(FakeParam(this=mono))
        self.assertIs(mono.tf, sdk_stubs.FakeTypefaceClass.MONOSPACE)
        p = FakeParam("text", 14.0, None)
        nf._FaceArgumentHook(self.owner, 2).before_hooked_method(p)
        self.assertIs(p.args[2], self.kit.faces["regular"])

    def test_activity_result_hook(self):
        picked = []
        self.owner.handle_picked = lambda uris, slot: picked.append((uris, slot))

        class Intent:
            def getClipData(self):
                return None

            def getData(self):
                return "content://x/font.ttf"
        hook = nf._PickerResultHook(self.owner)
        hook.before_hooked_method(FakeParam(nf.PICK_CODE + 3, -1, Intent()))
        hook.before_hooked_method(FakeParam(nf.PICK_CODE, 0, Intent()))
        hook.before_hooked_method(FakeParam(1234, -1, Intent()))
        self.assertEqual(picked, [(["content://x/font.ttf"], "bold")])

    def test_pick_dedupe(self):
        calls = []
        self.owner.intake_async = lambda sources, **kw: calls.append(sources)
        self.owner.handle_picked(["u1"], None)
        self.owner.handle_picked(["u1"], None)
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
        patcher = self.owner.paint_swap
        patcher._live_paints = lambda: iter(paints)
        patcher.swap_in(self.registry, self.kit)
        self.assertIs(paints[0].tf, self.kit.faces["regular"])
        self.assertIs(paints[1].tf, self.kit.faces["bold"])
        self.assertIs(paints[2].tf, Tf.MONOSPACE)
        self.assertIs(paints[3].tf, custom)
        self.registry.use_kit(None)
        patcher.swap_out(self.registry)
        self.assertIsNone(paints[0].tf)
        self.assertIs(paints[1].tf, Tf.DEFAULT_BOLD)


class SettingsTest(PluginTestBase):
    def test_settings_pages_build(self):
        items = self.owner.create_settings()
        texts = [getattr(i, "text", "") for i in items]
        self.assertIn("NelyFonts", texts)
        self.assertIn("Выбрать файлы шрифта", texts)
        self.assertIn("Шрифт не выбран", texts)
        self.assertFalse(any(i.kind == "Text" and "Ошибка" in i.text for i in items))
        self.assertTrue(self.owner._intake([("path", TTF)], None, "file"))
        texts = [getattr(i, "text", "") for i in self.owner.create_settings()]
        self.assertIn("First Coffee — активен", texts)
        for page in (self.owner._inspector_page, self.owner._faces_page, self.owner._downloads_page):
            self.assertTrue(page())
        report = self.owner._diagnostics()
        self.assertIn("First Coffee", report)

    def test_icons_exist_in_app(self):
        valid = {"msg_photo_text_regular", "msg_photo_text_framed3", "msg_openin", "msg_download", "msg_link",
                 "msg_fave", "msg_list", "msg_photo_text2", "msg_text_outlined", "msg_photo_text_framed",
                 "msg_customize", "msg_stats", "msg_retry", "msg_reset", "msg_delete", "msg_search",
                 "msg_copy", "msg_info"}
        self.assertTrue(self.owner._intake([("path", TTF)], None, "file"))
        items = list(self.owner.create_settings())
        for page in (self.owner._inspector_page, self.owner._faces_page, self.owner._downloads_page):
            items += page()
        for item in items:
            icon = getattr(item, "icon", None)
            if icon:
                self.assertIn(icon, valid)


class TelegramCacheTest(unittest.TestCase):
    def setUp(self):
        stubs = sdk_stubs
        stubs.FakeAU.reset()
        self.orig_regular = stubs.FakeAU.regular()
        self.orig_medium = stubs.FakeAU.bold()
        self.header = stubs.FakeTextView(self.orig_medium)
        self.cell = stubs.FakeTextView(self.orig_regular)
        self.plain = stubs.FakeTextView(None)
        self.mono = stubs.FakeTextView(stubs.FakeTypefaceClass.MONOSPACE)
        root = stubs.FakeViewGroup(self.header, stubs.FakeViewGroup(self.cell, self.plain, self.mono))
        stubs.FakeLaunchActivity.instance = stubs.FakeLaunchActivity(root)
        stubs.JCLASSES.update({
            nf.UTILS_CLS: stubs.FakeAU,
            "android.widget.TextView": stubs.FakeTextView,
            "android.view.ViewGroup": stubs.FakeViewGroup,
            "org.telegram.ui.LaunchActivity": stubs.FakeLaunchActivity,
        })
        nf.Reflect._memo[nf.UTILS_CLS] = stubs.FakeAUClass()
        self.tmp = tempfile.mkdtemp(prefix="nelyfonts-cache-")
        self.old_cwd = os.getcwd()
        os.chdir(self.tmp)
        self.owner = nf.NelyFonts()
        self.owner.on_plugin_load()

    def tearDown(self):
        self.owner.on_plugin_unload()
        for k in (nf.UTILS_CLS, "android.widget.TextView", "android.view.ViewGroup",
                  "org.telegram.ui.LaunchActivity"):
            sdk_stubs.JCLASSES.pop(k, None)
        nf.Reflect._memo.pop(nf.UTILS_CLS, None)
        os.chdir(self.old_cwd)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_cache_primed_and_views_patched(self):
        AU = sdk_stubs.FakeAU
        self.assertTrue(self.owner._intake([("path", TTF)], None, "file"))
        fs = self.owner.registry.kit
        self.assertIs(AU.regular(), fs.faces["regular"])
        self.assertIs(AU.bold(), fs.faces["medium"])
        self.assertIs(AU.getTypeface("fonts/ritalic.ttf"), fs.faces["italic"])
        self.assertIs(AU.getTypeface("fonts/rcondensedbold.ttf"), fs.faces["bold"])
        self.assertIsNot(AU.getTypeface("fonts/rmono.ttf"), fs.faces["regular"])
        self.assertIs(self.header.tf, fs.faces["medium"])
        self.assertIs(self.cell.tf, fs.faces["regular"])
        self.assertIs(self.plain.tf, fs.faces["regular"])
        self.assertIs(self.mono.tf, sdk_stubs.FakeTypefaceClass.MONOSPACE)
        self.assertGreaterEqual(self.owner.cached_count, 7)
        self.assertEqual(self.owner._screen_census()[:2], (3, 3))

    def test_reprime_after_external_clear(self):
        AU = sdk_stubs.FakeAU
        self.assertTrue(self.owner._intake([("path", TTF)], None, "file"))
        fs = self.owner.registry.kit
        AU.clearTypefaceCache()
        nf._CacheResetHook(self.owner).after_hooked_method(object())
        self.assertIs(AU.regular(), fs.faces["regular"])
        self.assertIs(AU.bold(), fs.faces["medium"])

    def test_disable_restores_originals(self):
        AU = sdk_stubs.FakeAU
        self.assertTrue(self.owner._intake([("path", TTF)], None, "file"))
        self.owner._disengage()
        core = self.owner.registry
        for tf in (AU.regular(), AU.bold(), self.header.tf, self.cell.tf, self.plain.tf):
            self.assertFalse(core.is_mine(tf), tf)
        self.assertEqual(core.role_of(self.header.tf), "medium")

    def test_switching_fonts_replaces_previous(self):
        AU = sdk_stubs.FakeAU
        self.assertTrue(self.owner._intake([("path", TTF)], None, "file"))
        self.assertTrue(self.owner._intake([("path", os.path.join(FIX, "variable_wght.ttf"))], None, "file"))
        fs = self.owner.registry.kit
        self.assertIn("variable_wght", str(fs.faces["regular"].src) + self.owner.vault.manifest["slots"]["regular"]["name"])
        self.assertIs(AU.regular(), fs.faces["regular"])
        self.assertIs(self.cell.tf, fs.faces["regular"])
        self.assertIs(self.header.tf, fs.faces["medium"])


class UnreachableCacheTest(TelegramCacheTest):
    def setUp(self):
        super().setUp()
        cls = sdk_stubs.FakeAUClass

        def no_field(_self, name):
            raise Exception("NoSuchFieldException: " + name)
        self._orig_get = cls.getDeclaredField
        cls.getDeclaredField = no_field
        cls.getDeclaredFields = lambda _self: []

    def tearDown(self):
        sdk_stubs.FakeAUClass.getDeclaredField = self._orig_get
        del sdk_stubs.FakeAUClass.getDeclaredFields
        super().tearDown()

    def test_cache_primed_and_views_patched(self):
        AU = sdk_stubs.FakeAU
        self.assertTrue(self.owner._intake([("path", TTF)], None, "file"))
        fs = self.owner.registry.kit
        self.assertEqual(self.owner.cached_count, 0)
        self.assertTrue(self.owner.cache_check.startswith("штатный"))
        stock = AU.regular()
        self.assertFalse(self.owner.registry.is_mine(stock))

        class Paint:
            def __init__(self, tf):
                self.tf = tf

            def getTypeface(self):
                return self.tf

            def setTypeface(self, tf):
                self.tf = tf

        class SimpleTextView:
            def __init__(self):
                self.paint = Paint(AU.regular())

            def getPaint(self):
                return self.paint

            def setTypeface(self, tf):
                self.paint.tf = tf

        online = SimpleTextView()
        nf._PaintHolderInitHook(self.owner).after_hooked_method(FakeParam(this=online))
        self.assertIs(online.paint.tf, fs.faces["regular"])
        paint = Paint(AU.regular())
        nf._ExteraPaintInitHook(self.owner).after_hooked_method(FakeParam(this=paint))
        self.assertIs(paint.tf, fs.faces["regular"])
        p = FakeParam(AU.bold())
        nf._PaintFaceSetterHook(self.owner).before_hooked_method(p)
        self.assertIs(p.args[0], fs.faces["medium"])
        p = FakeParam(sdk_stubs.FakeTypeface("emoji"))
        nf._PaintFaceSetterHook(self.owner).before_hooked_method(p)
        self.assertEqual(p.args[0].src, "emoji")
        self.assertIs(self.cell.tf, fs.faces["regular"])

    test_reprime_after_external_clear = None
    test_switching_fonts_replaces_previous = None


class MetadataTest(unittest.TestCase):
    def test_metadata(self):
        self.assertEqual(nf.__name__, "NelyFonts")
        self.assertEqual(nf.__id__, "nelyfonts")
        self.assertRegex(nf.__version__, r"^\d+\.\d+\.\d+$")


if __name__ == "__main__":
    unittest.main()
