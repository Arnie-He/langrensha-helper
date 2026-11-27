# -*- coding: utf-8 -*-
"""手机端脚本的模拟测试：把 public/app.js 放进系统自带的 JavaScript 引擎里跑（见 tests/client_sim.js）。

只有 macOS 自带这个引擎（jsc）；别的系统上这组测试自动跳过。
运行： python3 -m unittest discover -s tests
"""
import os
import subprocess
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
JSC = '/System/Library/Frameworks/JavaScriptCore.framework/Versions/Current/Helpers/jsc'


@unittest.skipUnless(os.path.exists(JSC), '这台机器没有 jsc（只有 macOS 自带）')
class Client(unittest.TestCase):
    def test_client_simulation(self):
        r = subprocess.run([JSC, os.path.join('tests', 'client_sim.js')], cwd=ROOT,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=300)
        out = r.stdout.decode('utf-8', 'replace')
        bad = [line for line in out.splitlines() if not line.startswith('ok ')]
        self.assertEqual(r.returncode, 0, '\n' + '\n'.join(bad))
        self.assertIn(' 通过', out)
        self.assertNotIn('FAIL', out)

    def test_scripts_parse(self):
        for f in ('public/app.js', 'public/fx.js'):
            r = subprocess.run([JSC, '-e', "checkSyntax('%s')" % f], cwd=ROOT,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
            self.assertEqual(r.returncode, 0, f + '\n' + r.stdout.decode('utf-8', 'replace'))


if __name__ == '__main__':
    unittest.main()
