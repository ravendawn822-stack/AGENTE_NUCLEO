import unittest,json
from model import *
from engine import *
from protocol import suite,check,interpolation
class Tests(unittest.TestCase):
    def test_scores(self):
        s=new_skill((3,(11,0),(11,0)),1,[])
        a=score(s,[4,1,0,1,4],[.45,.35,.2])
        self.assertEqual(a['P'],.5);self.assertEqual(a['E'],1)
        self.assertTrue(all(0<=v<=1 for v in a.values()))
        self.assertAlmostEqual(a['S'],(.45*a['P']+.35*a['R']+.2*a['E'])/(1+a['K']))
    def test_freeze_and_bounds(self):
        cfg=dict(DEFAULT,candidates=160);m=[new_skill((3,(11,0),(11,0)),1,[])]
        before=json.dumps(m);ev=[]
        a,x=solve(lambda x:x*x,m,'C','candidates',cfg,7,ev.append)
        b,y=solve(lambda x:x*x,m,'C','candidates',cfg,7)
        self.assertEqual(a,b);self.assertEqual(x['candidates'],y['candidates']);self.assertEqual(before,json.dumps(m))
        self.assertLessEqual(x['candidates'],160);self.assertLessEqual(depth(a),4)
        self.assertTrue(x['constructed']);self.assertEqual(x['constructed'],x['present'])
    def test_refutation(self):
        cfg=dict(DEFAULT,candidates=100);mem=[]
        b,m=solve(lambda x:x,mem,'A','candidates',cfg,0)
        ok,e=learn(mem,b,m,lambda x:x+1,1,16)
        self.assertFalse(ok);self.assertEqual(mem,[])
    def test_suites(self):
        a,b=suite(99);self.assertEqual((a,b),suite(99))
        sig=lambda e:tuple(value(e,x) for x in range(-4,5))
        self.assertEqual(len({sig(e) for e in a+b}),200)
        self.assertTrue(interpolation(b[0]))
    def test_boolean(self):
        e=(30,(20,(11,0),(11,1)),(1,(11,0),(10,1)),(11,1))
        self.assertEqual(value(e,(2,5)),3);self.assertEqual(value(e,(7,5)),5)
if __name__=='__main__':unittest.main()
