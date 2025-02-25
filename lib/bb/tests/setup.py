#
# Copyright BitBake Contributors
#
# SPDX-License-Identifier: GPL-2.0-only
#

from bb.tests.fetch import FetcherTest

class BitbakeSetupTest(FetcherTest):
    def setUp(self):
        super(BitbakeSetupTest, self).setUp()

        self.topdir = os.path.join(self.tempdir, "bitbake-builds")

        self.registrypath = os.path.join(self.tempdir, "bitbake-setup-configurations")

        os.makedirs(self.registrypath)
        self.git_init(cwd=self.registrypath)
        self.git('commit --allow-empty -m "Initial commit"', cwd=self.registrypath)

        self.testrepopath = os.path.join(self.tempdir, "test-repo")
        os.makedirs(self.testrepopath)
        self.git_init(cwd=self.testrepopath)
        self.git('commit --allow-empty -m "Initial commit"', cwd=self.testrepopath)

        oesetupbuild = """#!/usr/bin/env python3
import getopt
import sys
import os
import shutil
opts, args = getopt.getopt(sys.argv[2:], "c:b:", "no-shell")
for option, value in opts:
    if option == '-c':
        template = value
    if option == '-b':
        builddir = value
confdir = os.path.join(builddir, 'conf')
os.makedirs(confdir, exist_ok=True)
with open(os.path.join(confdir, 'conf-summary.txt'), 'w') as f:
    f.write(template)
shutil.copy(os.path.join(os.path.dirname(__file__), 'test-repo/test-file'), confdir)
with open(os.path.join(builddir, 'init-build-env'), 'w') as f:
    f.write("BBPATH={}\\nexport BBPATH\\nPATH={}:$PATH".format(builddir, os.path.join(os.path.dirname(__file__), 'test-repo/scripts')))
"""
        self.add_file_to_testrepo('scripts/oe-setup-build', oesetupbuild, script=True)

        bitbakeconfigbuild = """#!/usr/bin/env python3
import os
import sys
confdir = os.path.join(os.environ['BBPATH'], 'conf')
fragment = sys.argv[2]
with open(os.path.join(confdir, fragment), 'w') as f:
    f.write('')
"""
        self.add_file_to_testrepo('scripts/bitbake-config-build', bitbakeconfigbuild, script=True)

        sometargetexecutable_template = """#!/usr/bin/env python3
import os
print("This is {}")
print("BBPATH is {{}}".format(os.environ["BBPATH"]))
"""
        for e_name in ("some-target-executable-1", "some-target-executable-2"):
            sometargetexecutable = sometargetexecutable_template.format(e_name)
            self.add_file_to_testrepo('scripts/{}'.format(e_name), sometargetexecutable, script=True)

    def runbbsetup(self, cmd):
        bbsetup = os.path.abspath(os.path.dirname(__file__) +  "/../../../bin/bitbake-setup")
        return bb.process.run("{} {}".format(bbsetup, cmd))

    def add_json_config_to_registry(self, name, rev):
        config = """
{
    "sources": {
        "test-repo": {
            "git-remote": {
                "remotes": {
                    "origin": {
                        "uri": "file://%s"
                    }
                },
                "rev": "%s"
            },
            "path": "test-repo"
        }
    },
    "description": "Test configuration",
    "bitbake-setup": {
        "configuration": {
            "gadget": {
                "description": "Gadget build configuration",
                "oe-template": "test-configuration-gadget",
                "oe-fragments": ["test-fragment-1"],
                "targets": ["some-target-executable-1"]
            },
            "gizmo": {
                "description": "Gizmo build configuration",
                "oe-template": "test-configuration-gizmo",
                "oe-fragments": ["test-fragment-2"],
                "targets": ["some-target-executable-2"]
            }
        }
    },
    "version": "1.0"
}
""" % (self.testrepopath, rev)
        os.makedirs(os.path.join(self.registrypath, os.path.dirname(name)), exist_ok=True)
        with open(os.path.join(self.registrypath, name), 'w') as f:
            f.write(config)
        self.git('add {}'.format(name), cwd=self.registrypath)
        self.git('commit -m "Adding {}"'.format(name), cwd=self.registrypath)
        import json
        return json.loads(config)

    def add_file_to_testrepo(self, name, content, script=False):
        fullname = os.path.join(self.testrepopath, name)
        os.makedirs(os.path.join(self.testrepopath, os.path.dirname(name)), exist_ok=True)
        with open(fullname, 'w') as f:
            f.write(content)
        if script:
            import stat
            st = os.stat(fullname)
            os.chmod(fullname, st.st_mode | stat.S_IEXEC)
        self.git('add {}'.format(name), cwd=self.testrepopath)
        self.git('commit -m "Adding {}"'.format(name), cwd=self.testrepopath)

    def check_builddir_files(self, buildpath, test_file_content, json_config):
        with open(os.path.join(buildpath, 'layers', 'test-repo', 'test-file')) as f:
            self.assertEqual(f.read(), test_file_content)
        for c,v in json_config["bitbake-setup"]["configuration"].items():
            bb_build_path = os.path.join(buildpath, 'build-{}'.format(c))
            bb_conf_path = os.path.join(bb_build_path, 'conf')
            self.assertTrue(os.path.exists(os.path.join(bb_build_path, 'init-build-env')))

            out = bb.process.run(os.path.join(bb_build_path, 'build-targets'))
            for t in v["targets"]:
                self.assertIn("This is {}".format(t), out[0])
            self.assertIn("BBPATH is {}".format(bb_build_path), out[0])

            with open(os.path.join(bb_conf_path, 'conf-summary.txt')) as f:
                self.assertEqual(f.read(), v["oe-template"])

            for f in v["oe-fragments"]:
                self.assertTrue(os.path.exists(os.path.join(bb_conf_path, f)))

            with open(os.path.join(bb_conf_path, 'test-file')) as f:
                self.assertEqual(f.read(), test_file_content)

    def test_setup(self):
        # check that no arguments works
        self.runbbsetup("")

        # check that --help works
        self.runbbsetup("--help")

        # check that writing settings works and then adjust them to point to
        # test registry repo
        out = self.runbbsetup("reset-settings --top-dir {}".format(self.topdir))
        settings_path = "{}/bitbake-setup.conf".format(self.topdir)
        self.assertIn(settings_path, out[0])
        out = self.runbbsetup("change-setting --top-dir {} default registry 'git://{};protocol=file;branch=master;rev=master'".format(self.topdir, self.registrypath))
        self.assertIn("Setting 'registry' in section 'default' is changed to", out[0])
        self.assertIn("New settings written to".format(settings_path), out[0])

        # check that 'list' produces correct output with no configs, one config and two configs
        out = self.runbbsetup("list --top-dir {}".format(self.topdir))
        self.assertNotIn("test-config-1", out[0])
        self.assertNotIn("test-config-2", out[0])

        json_1 = self.add_json_config_to_registry('test-config-1.conf.json', 'master')
        out = self.runbbsetup("list --top-dir {}".format(self.topdir))
        self.assertIn("test-config-1", out[0])
        self.assertNotIn("test-config-2", out[0])

        json_2 = self.add_json_config_to_registry('config-2/test-config-2.conf.json', 'master')
        out = self.runbbsetup("list --top-dir {}".format(self.topdir))
        self.assertIn("test-config-1", out[0])
        self.assertIn("test-config-2", out[0])

        # check that init/status/update work
        # (the latter two should do nothing and say that config hasn't changed)
        test_file_content = 'initial\n'
        self.add_file_to_testrepo('test-file', test_file_content)
        out = self.runbbsetup("init test-config-1 --top-dir {}".format(self.topdir))
        buildpath = os.path.join(self.topdir, 'test-config-1')
        self.check_builddir_files(buildpath, test_file_content, json_1)
        os.environ['BBPATH'] = os.path.join(buildpath, 'build')
        out = self.runbbsetup("status")
        self.assertIn("Configuration in {} has not changed".format(buildpath), out[0])
        out = self.runbbsetup("update")
        self.assertIn("Configuration in {} has not changed".format(buildpath), out[0])

        # change a file in the test layer repo, make a new commit and
        # test that status/update correctly report the change and update the config
        prev_test_file_content = test_file_content
        test_file_content = 'modified\n'
        self.add_file_to_testrepo('test-file', test_file_content)
        out = self.runbbsetup("status")
        self.assertIn("Layer repository file://{} checked out into {}/layers/test-repo updated revision master from".format(self.testrepopath, buildpath), out[0])
        out = self.runbbsetup("update")
        self.assertIn("Existing bitbake configuration directory renamed to {}/build-gadget/conf-backup.".format(buildpath), out[0])
        self.assertIn("Existing bitbake configuration directory renamed to {}/build-gizmo/conf-backup.".format(buildpath), out[0])
        self.assertIn('-{}+{}'.format(prev_test_file_content, test_file_content), out[0])
        self.check_builddir_files(buildpath, test_file_content, json_1)

        # make a new branch in the test layer repo, change a file on that branch,
        # make a new commit, update the top level json config to refer to that branch,
        # and test that status/update correctly report the change and update the config
        prev_test_file_content = test_file_content
        test_file_content = 'modified-in-branch\n'
        branch = "another-branch"
        self.git('checkout -b {}'.format(branch), cwd=self.testrepopath)
        self.add_file_to_testrepo('test-file', test_file_content)
        json_1 = self.add_json_config_to_registry('test-config-1.conf.json', branch)
        out = self.runbbsetup("status")
        self.assertIn("Configuration in {} has changed:".format(buildpath), out[0])
        self.assertIn('-                "rev": "master"\n+                "rev": "another-branch"', out[0])
        out = self.runbbsetup("update")
        self.assertIn("Existing bitbake configuration directory renamed to {}/build-gadget/conf-backup.".format(buildpath), out[0])
        self.assertIn("Existing bitbake configuration directory renamed to {}/build-gizmo/conf-backup.".format(buildpath), out[0])
        self.assertIn('-{}+{}'.format(prev_test_file_content, test_file_content), out[0])
        self.check_builddir_files(buildpath, test_file_content, json_1)
