import os, collections, json
from twisted.trial import unittest
from .common import BasedirMixin, NodeRunnerMixin, TwoNodeMixin, fake_transport
from ..eventual import flushEventualQueue
from ..errors import CommandError
from ..invitation import splitMessages

MROW = collections.namedtuple("Row", ["my", "theirs", "next"])
AddressbookRow = collections.namedtuple("AddressbookEntry",
                                        ["petname", "their_verfkey", "acked",
                                         "my_CID_key",
                                         "their_channel_record",
                                         ])

class Invite(BasedirMixin, NodeRunnerMixin, unittest.TestCase):
    def checkCounts(self, node, code, my, theirs, next, exists=True):
        c = node.db.execute("SELECT"
                            " myMessages, theirMessages, nextExpectedMessage"
                            " FROM invitations WHERE code=?",
                            (code.encode("hex"),))
        rows = [ MROW(splitMessages(row[0]), splitMessages(row[1]), row[2])
                 for row in c.fetchall() ]
        if not exists:
            self.failUnlessEqual(len(rows), 0)
            return
        self.failUnlessEqual(len(rows), 1)
        self.failUnlessEqual(len(rows[0].my), my)
        self.failUnlessEqual(len(rows[0].theirs), theirs)
        self.failUnlessEqual(rows[0].next, next)
        return rows

    def fetchAddressBook(self, node):
        c = node.db.execute("SELECT petname, their_verfkey, acked,"
                            "       my_CID_key, their_channel_record_json"
                            " FROM addressbook")
        rows = [ AddressbookRow(row[0], str(row[1]), bool(row[2]),
                                str(row[3]), json.loads(row[4]))
                 for row in c.fetchall() ]
        return rows

    def test_one(self):
        code = "code"

        basedir1 = os.path.join(self.make_basedir(), "node1")
        self.createNode(basedir1)
        n1 = self.startNode(basedir1, beforeStart=self.disable_polling)
        rclient1 = list(n1.client.im)[0]
        tport1 = fake_transport()
        tports1 = {0: tport1[1]}

        nA_notices = []
        n1.client.subscribe("addressbook", nA_notices.append)

        n1.client.command_invite(u"petname-from-1", code,
                                 override_transports=tports1)
        inviteID = rclient1.subscriptions.keys()[0]
        rdir = os.path.join(rclient1.basedir, inviteID)
        self.failUnless(os.path.exists(rdir))
        # messages: node1-M1
        # at this point, node1 should have sent a single message (M1), and
        # should be waiting for the peer's first message (M1)
        self.checkCounts(n1, code, 1, 0, 1)

        # polling again should ignore the previously-sent message
        rclient1.poll()
        self.checkCounts(n1, code, 1, 0, 1)

        # now we add a peer (node2) for them to talk to
        basedir2 = os.path.join(self.make_basedir(), "node2")
        self.createNode(basedir2)
        n2 = self.startNode(basedir2, beforeStart=self.disable_polling)
        tport2 = fake_transport()
        tports2 = {0: tport2[1]}
        n2.client.command_invite(u"petname-from-2", code,
                                 override_transports=tports2)
        rclient2 = list(n2.client.im)[0]
        # messages: node1-M1, node2-M1

        # node2 should have sent one message. node1 should not have noticed
        # yet, because we only poll manually here.
        self.checkCounts(n2, code, 1, 0, 1)
        self.checkCounts(n1, code, 1, 0, 1)

        # allow node2 to poll. It should see the node1's first message, and
        # create its own second message. node1 should not notice yet.
        rclient2.poll()
        # messages: node1-M1, node2-M1, node2-M2
        self.checkCounts(n1, code, 1, 0, 1)
        self.checkCounts(n2, code, 2, 1, 2)

        # node2 polling again should not change anything
        rclient2.poll()
        self.checkCounts(n1, code, 1, 0, 1)
        self.checkCounts(n2, code, 2, 1, 2)

        # let node1 poll. It will see both of node2's messages, add its
        # addressbook entry, send it's second and third messages, and be
        # waiting for an ACK
        #print "== first client polling to get M2"
        rclient1.poll()
        # messages: node1-M1, node2-M1, node2-M2, node1-M2, node1-M3-ACK
        self.checkCounts(n2, code, 2, 1, 2)
        self.checkCounts(n1, code, 3, 2, 3)

        a1 = self.fetchAddressBook(n1)
        self.failUnlessEqual(len(a1), 1)
        self.failUnlessEqual(a1[0].petname, "petname-from-1")
        self.failUnlessEqual(a1[0].acked, False)
        #print a1[0].their_verfkey
        #print a1[0].their_channel_record

        # re-polling should not do anything
        rclient1.poll()
        # TODO: the Invitation is incorrectly given new messages here
        self.checkCounts(n2, code, 2, 1, 2)
        self.checkCounts(n1, code, 3, 2, 3)

        # let node2 poll. It will see node1's M2 message, add its addressbook
        # entry, send its ACK, will see node1's ACK, update its addressbook
        # entry, send its destroy-channel message, and delete the invitation.
        #print " == second client polling to get M2"
        rclient2.poll()
        # messages: node1-M1, node2-M1, node2-M2, node1-M2, node1-M3-ACK,
        # node2-M3-ACK, node2-M4-destroy
        self.checkCounts(n2, code, None, None, None, exists=False)
        self.checkCounts(n1, code, 3, 2, 3)
        a2 = self.fetchAddressBook(n2)
        self.failUnlessEqual(len(a2), 1)
        self.failUnlessEqual(a2[0].petname, "petname-from-2")
        self.failUnlessEqual(a2[0].acked, True)

        # finally, let node1 poll one last time. It will see the ACK and send
        # the second destroy-channel message.
        rclient1.poll()
        # messages: node1-M1, node2-M1, node2-M2, node1-M2, node1-M3-ACK,
        # node2-M3-ACK, node2-M4-destroy, node1-M4-destroy
        self.checkCounts(n2, code, None, None, None, exists=False)
        self.checkCounts(n1, code, None, None, None, exists=False)
        a1 = self.fetchAddressBook(n1)
        self.failUnlessEqual(len(a1), 1)
        self.failUnlessEqual(a1[0].acked, True)

        self.failUnlessEqual(a1[0].their_channel_record["CID_key"],
                             a2[0].my_CID_key)
        self.failUnlessEqual(a1[0].my_CID_key,
                             a2[0].their_channel_record["CID_key"])

        # finally check that the channel has been destroyed
        self.failIf(os.path.exists(rdir))

        # look at some client command handlers too
        a1 = n1.client.command_list_addressbook()
        self.failUnlessEqual(len(a1), 1)
        a2 = n2.client.command_list_addressbook()
        self.failUnlessEqual(len(a2), 1)
        self.failUnlessEqual(a1[0]["my_verfkey"], a2[0]["their_verfkey"])
        self.failUnlessEqual(a2[0]["my_verfkey"], a1[0]["their_verfkey"])
        self.failUnlessEqual(a1[0]["acked"], True)
        self.failUnlessEqual(a1[0]["petname"], "petname-from-1")
        self.failUnlessEqual(a2[0]["acked"], True)
        self.failUnlessEqual(a2[0]["petname"], "petname-from-2")

        self.failUnlessEqual(nA_notices, [])
        d = flushEventualQueue()
        def _then(_):
            self.failUnlessEqual(len(nA_notices), 2)
            self.failUnlessEqual(nA_notices[0].action, "insert")
            self.failUnlessEqual(nA_notices[0].new_value["acked"], 0)
            self.failUnlessEqual(nA_notices[0].new_value["petname"],
                                 "petname-from-1")
            self.failUnlessEqual(nA_notices[1].action, "update")
            self.failUnlessEqual(nA_notices[1].new_value["acked"], 1)
            self.failUnlessEqual(nA_notices[1].new_value["petname"],
                                 "petname-from-1")
            n1.client.unsubscribe("addressbook", nA_notices.append)
        d.addCallback(_then)
        return d

    def test_duplicate_code(self):
        basedir1 = os.path.join(self.make_basedir(), "node1")
        self.createNode(basedir1)
        n1 = self.startNode(basedir1, beforeStart=self.disable_polling)
        code = "code"
        tport = fake_transport()
        tports = {0: tport[1]}
        n1.client.command_invite(u"petname-from-1", code,
                                 override_transports=tports)
        self.failUnlessRaises(CommandError,
                              n1.client.command_invite, u"new-petname", code)


class Two(TwoNodeMixin, unittest.TestCase):
    def test_two(self):
        nA, nB, entA, entB = self.make_nodes()
        self.failUnlessEqual(nA.client.command_list_addressbook()[0]["cid"],
                             entA["id"])
        self.failUnlessEqual(nB.client.command_list_addressbook()[0]["cid"],
                             entB["id"])
