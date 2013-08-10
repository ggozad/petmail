import os, collections, json
from twisted.trial import unittest
from .common import BasedirMixin, NodeRunnerMixin
from ..invitation import splitMessages

MROW = collections.namedtuple("Row", ["my", "theirs", "next"])
AddressbookRow = collections.namedtuple("AddressbookEntry",
                                        ["petname", "their_verfkey",
                                         "their_tport", "acked"])

class Invite(BasedirMixin, NodeRunnerMixin, unittest.TestCase):
    def disable_polling(self, n):
        list(n.client.im)[0].enable_polling = False

    def checkCounts(self, node, code, my, theirs, next, exists=True):
        c = node.db.cursor()
        c.execute("SELECT myMessages, theirMessages, nextExpectedMessage"
                  " FROM invitations WHERE code_hex=?", (code.encode("hex"),))
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
        c = node.db.cursor()
        c.execute("SELECT petname, their_verfkey, their_transport_record_json,"
                  " acked"
                  " FROM addressbook")
        rows = [ AddressbookRow(row[0], row[1], json.loads(row[2]),
                                bool(row[3]))
                 for row in c.fetchall() ]
        return rows

    def test_one(self):
        basedir1 = os.path.join(self.make_basedir(), "node1")
        self.createNode(basedir1)
        n1 = self.startNode(basedir1, beforeStart=self.disable_polling)
        code = "code"
        n1.client.command_invite(u"petname-from-1", code)
        # at this point, node1 should have sent a single message, and should
        # be waiting for the peer's first message
        self.checkCounts(n1, code, 1, 0, 1)

        # polling again should ignore the previously-sent message
        list(n1.client.im)[0].poll()
        self.checkCounts(n1, code, 1, 0, 1)

        # now we add a peer (node2) for them to talk to
        basedir2 = os.path.join(self.make_basedir(), "node2")
        self.createNode(basedir2)
        n2 = self.startNode(basedir2, beforeStart=self.disable_polling)
        n2.client.command_invite(u"petname-from-2", code)

        # node2 should have sent one message. node1 should not have noticed
        # yet, because we only poll manually here.
        self.checkCounts(n2, code, 1, 0, 1)
        self.checkCounts(n1, code, 1, 0, 1)

        # allow node2 to poll. It should see the node1's first message, and
        # create its own second message. node1 should not notice yet.
        list(n2.client.im)[0].poll()
        self.checkCounts(n1, code, 1, 0, 1)
        self.checkCounts(n2, code, 2, 1, 2)

        # node2 polling again should not change anything
        list(n2.client.im)[0].poll()
        self.checkCounts(n1, code, 1, 0, 1)
        self.checkCounts(n2, code, 2, 1, 2)

        # let node1 poll. It will see both of node2's messages, add its
        # addressbook entry, send it's second and third messages, and be
        # waiting for an ACK
        print "== first client polling to get M2"
        list(n1.client.im)[0].poll()
        self.checkCounts(n2, code, 2, 1, 2)
        self.checkCounts(n1, code, 3, 2, 3)

        a1 = self.fetchAddressBook(n1)
        self.failUnlessEqual(len(a1), 1)
        self.failUnlessEqual(a1[0].petname, "petname-from-1")
        self.failUnlessEqual(a1[0].acked, False)
        #print a1[0].their_verfkey
        #print a1[0].their_tport

        # re-polling should not do anything
        list(n1.client.im)[0].poll()
        # TODO: the Invitation is incorrectly given new messages here
        self.checkCounts(n2, code, 2, 1, 2)
        self.checkCounts(n1, code, 3, 2, 3)

        # let node2 poll. It will do the same, and will also see the ACK and
        # send its destroy-channel message, and delete the invitation.
        list(n2.client.im)[0].poll()
        self.checkCounts(n2, code, None, None, None, exists=False)
        self.checkCounts(n1, code, 3, 2, 3)
