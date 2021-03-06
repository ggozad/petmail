from twisted.trial import unittest
from .. import rrid

def flip_bit(s):
    return s[:-1] + chr(ord(s[-1]) ^ 0x01)

class RRID(unittest.TestCase):
    def test_create(self):
        binary = type(b"")
        tokenid, privkey, token0 = rrid.create()
        self.failUnlessEqual((type(tokenid), type(privkey), type(token0)),
                             (binary, binary, binary))
        self.failUnlessEqual(len(tokenid), 32)
        self.failUnlessEqual(len(privkey), 32)
        self.failUnlessEqual(len(token0), 3*32)

    def failUnlessDistinct(self, *things):
        self.failUnlessEqual(len(set(things)), len(things))

    def test_crypt(self):
        tokenid, privkey, token0 = rrid.create()
        token1 = rrid.randomize(token0)
        token2 = rrid.randomize(token1)
        self.failUnlessDistinct(token0, token1, token2)

        self.failUnlessEqual(rrid.decrypt(privkey, token0), tokenid)
        self.failUnlessEqual(rrid.decrypt(privkey, token1), tokenid)
        self.failUnlessEqual(rrid.decrypt(privkey, token2), tokenid)

        # tokens are malleable, we must tolerate that
        corrupt_token = flip_bit(token1)
        self.failIfEqual(rrid.decrypt(privkey, corrupt_token), tokenid)

        other_tokenid, other_privkey, other_token0 = rrid.create()
        other_token1 = rrid.randomize(other_token0)
        # disabled until rrid.py has real crypto
        #self.failIfEqual(rrid.decrypt(other_privkey, token1), tokenid)
        self.failIfEqual(rrid.decrypt(other_privkey, token1), other_tokenid)
        self.failIfEqual(rrid.decrypt(privkey, other_token1), tokenid)
        #self.failIfEqual(rrid.decrypt(privkey, other_token1), other_tokenid)
