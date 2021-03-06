import os
from twisted.application import service
from StringIO import StringIO
from nacl.public import PrivateKey
from ..scripts import runner, startstop
from ..scripts.create_node import create_node
from .. import rrid

class BasedirMixin:
    def make_basedir(self):
        # TestCase.mktemp() creates _trial_temp/MODULE/CLASS/TEST/RANDOM and
        # returns join(that,"temp"). We just want the part that ends with
        # TEST. So we rmdir the RANDOM and return .../TEST
        basedir = self.mktemp()
        random = os.path.dirname(basedir)
        os.rmdir(random)
        test = os.path.dirname(random)
        return test

class NodeRunnerMixin:
    def setUp(self):
        self.sparent = service.MultiService()
        self.sparent.startService()

    def tearDown(self):
        return self.sparent.stopService()

    def createNode(self, basedir):
        so = runner.CreateNodeOptions()
        so.parseOptions([basedir])
        out,err = StringIO(), StringIO()
        rc = create_node(so, out, err)
        self.failUnlessEqual(rc, 0, (rc, out, err))
        return rc, out ,err

    def startNode(self, basedir, beforeStart=None):
        so = runner.StartNodeOptions()
        so.parseOptions([basedir])
        p = startstop.MyPlugin(basedir, os.path.join(basedir, "petmail.db"))
        n = p.makeService(so)
        if beforeStart:
            beforeStart(n)
        n.setServiceParent(self.sparent)
        return n

    def disable_polling(self, n):
        list(n.client.im)[0].enable_polling = False

def fake_transport():
    privkey = PrivateKey.generate()
    pubkey_hex = privkey.public_key.encode().encode("hex")
    TID_tokenid, TID_privkey, TID_token0 = rrid.create()
    private = {"privkey": privkey,
               "TID": (TID_tokenid, TID_privkey, TID_token0) }
    # this is what lives in our database. All channels that share the same
    # transport will use the same thing.
    db_record = { "for_sender": {"type": "test-return",
                                 "transport_pubkey": pubkey_hex,
                                 },
                  "for_recipient": {"TID": TID_token0.encode("hex") },
                  }
    return private, db_record


class TwoNodeMixin(BasedirMixin, NodeRunnerMixin):
    def make_nodes(self, transport="test-return"):
        basedirA = os.path.join(self.make_basedir(), "nodeA")
        self.createNode(basedirA)
        nA = self.startNode(basedirA, beforeStart=self.disable_polling)

        basedirB = os.path.join(self.make_basedir(), "nodeB")
        self.createNode(basedirB)
        nB = self.startNode(basedirB, beforeStart=self.disable_polling)

        if transport == "test-return":
            self.tport1 = fake_transport()
            self.tports1 = {0: self.tport1[1]}
            self.tport2 = fake_transport()
            self.tports2 = {0: self.tport2[1]}
        elif transport == "local":
            nA.client.command_enable_local_mailbox()
            nB.client.command_enable_local_mailbox()
            self.tports1 = None
            self.tports2 = None
        else:
            raise KeyError("huh?")

        entA, entB = self.add_new_channel(nA, nB)
        return nA, nB, entA, entB

    def add_new_channel(self, nA, nB):
        rclientA = list(nA.client.im)[0]
        rclientB = list(nB.client.im)[0]
        code = "code"
        nA.client.command_invite(u"petname-from-A", code,
                                 override_transports=self.tports1)
        nB.client.command_invite(u"petname-from-B", code,
                                 override_transports=self.tports2)

        rclientA.poll()
        rclientB.poll()

        rclientA.poll()
        rclientB.poll()

        rclientA.poll()
        rclientB.poll()

        entA = nA.db.execute("SELECT * FROM addressbook").fetchone()
        entB = nB.db.execute("SELECT * FROM addressbook").fetchone()

        return entA, entB
