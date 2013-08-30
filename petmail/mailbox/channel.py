import re, struct, json, os
from hashlib import sha256
from .. import rrid
from ..errors import SilentError
from ..util import split_into, equal, netstring
from ..hkdf import HKDF
from nacl.public import PrivateKey, PublicKey, Box
from nacl.signing import SigningKey, VerifyKey
from nacl.secret import SecretBox
from nacl.exceptions import CryptoError

# msgC:
#  c0:
#  CIDToken =HKDF(CIDKey+seqnum) [fixed length]
#  netstring(CIDBox) =secretbox(key=CIDKey, seqnum+H(msgD)+channel-current)
#  msgD
# msgD:
#  pubkey2 [fixed length]
#  enc(to=channel-current, from=key2, msgE)
# msgE:
#  seqnum [fixed length]
#  netstring(sign(by=sender-signkey, pubkey2))
#  encoded-payload

class ChannelManager:
    """I receive inbound messages from transports, figure out which channel
    they're directed to, then I will create a Channel instance and pass it
    the message for decryption and delivery.

    For each message, I am told which transport it arrived on. I will only
    use channels that are connected to that transport. This protects against
    correlation attacks that combine a transport descriptor from one peer
    with a channel descriptor from a different one, in the hopes of proving
    that the two peers are actually the same.
    """

    def __init__(self, db):
        self.db = db
        self.CID_privkey = "??"

    def msgC_received(self, transportID, msgC):
        PREFIX = "c0:"
        if not msgC.startswith(PREFIX):
            raise ValueError("msgC doesn't start with '%s'" % PREFIX)
        splitpoints = [len(PREFIX), rrid.TOKEN_LENGTH, 32]
        _, MCID, pubkey2, enc = split_into(msgC, splitpoints, plus_trailer=True)
        ichannel = self.lookup(transportID, MCID)
        ichannel.msgC2_received(pubkey2, enc)

    def lookup(self, transportID, MCID):
        CID = rrid.decrypt(self.CID_privkey, MCID)
        # look through DB for the addressbook entry
        c = self.db.cursor()
        c.execute("SELECT their_verfkey FROM addressbook"
                  " WHERE my_private_CID=?", (CID,))
        results = c.fetchall()
        if not results:
            raise SilentError("unknown CID")
        their_verfkey_hex = results[0][0]
        # return an InboundChannel object for it
        return InboundChannel(self.db, their_verfkey_hex)

class InboundChannel:
    """I am given a msgC. I will decrypt it, update the channel database
    records as necessary, and finally dispatch the payload to a handler.
    """
    def __init__(self, db, channelID, channel_pubkey):
        self.db = db
        self.channelID = channelID # addressbook.id
        # do a DB fetch, grab everything we need
        c = self.db.cursor()
        c.execute("SELECT"
                  " my_old_channel_privkey, my_new_channel_privkey,"
                  " their_verfkey"
                  " FROM addressbook WHERE id=?", (channelID,))
        row = c.fetchone()
        self.my_new_channel_privkey = PrivateKey(row["my_old_channel_privkey"].decode("hex"))
        self.my_old_channel_privkey = PrivateKey(row["my_new_channel_privkey"].decode("hex"))
        self.their_verfkey = VerifyKey(row["their_verfkey"].decode("hex"))

    def msgC2_received(self, pubkey2, enc):
        # try both channel keys, new one first
        pub = PublicKey(pubkey2)
        b = Box(self.my_new_channel_privkey, pub)
        they_used_new_channel_key = False
        try:
            msgD = b.decrypt(enc)
            they_used_new_channel_key = True
        except CryptoError:
            # try the old key
            try:
                b = Box(self.my_old_channel_privkey, pub)
                msgD = b.decrypt(enc)
            except CryptoError:
                raise SilentError("neither channel key worked")
        if they_used_new_channel_key:
            c = self.db.cursor()
            c.execute("UPDATE addressbook SET they_used_new_channel_key=1"
                      " WHERE id=?", (self.channelID,))
            self.db.commit()

        # now parse and process msgD
        # msgD: sign(by=sender-signkey,pubkey2) + body
        # netstring plus trailer
        mo = re.search(r'^(\d+):', msgD)
        if not mo:
            raise SilentError("msgD lacks a netstring header")
        p1_len = int(mo.group(1))
        h,sm,comma,body = split_into([len(mo.group(1))+1, # netstring header
                                      p1_len, # signed message
                                      1, # netstring trailer comma
                                      ], plus_trailer=True)
        if comma != ",":
            raise SilentError("msgD has bad netstring trailer")
        m = self.their_verfkey.verify(sm)
        # 'm' is supposed to contain the ephemeral pubkey used in the
        # enclosing encrypted box. This confirms (to us) that the addressbook
        # peer really did want to send this message, without enabling us to
        # convince anyone else of this fact.
        if not equal(m, pubkey2):
            raise SilentError("msgD authentication check failed")

        # ok, body is good
        self.bodyReceived(body)

    def bodyReceived(self, body):
        pass

assert struct.calcsize(">Q") == 64

class OutboundChannel:
    # I am created to send messages.
    def __init__(self, db, cid):
        self.db = db
        self.cid = cid

    def send(self, payload):
        c = self.db.cursor()
        c.execute("SELECT next_outbound_seqnum, my_signkey,"
                  " their_channel_pubkey, their_CID_key"
                  " FROM addressbook WHERE id=?", (self.cid,))
        res = c.fetchone()
        assert res, "missing cid"
        next_outbound_seqnum = res[0]
        c.execute("UPDATE addressbook SET next_outbound_seqnum=? WHERE id=?",
                  (next_outbound_seqnum+1, self.cid))
        self.db.commit()
        seqnum_s = struct.pack(">Q", next_outbound_seqnum)
        my_signkey = SigningKey(res[1].decode("hex"))
        privkey2 = PrivateKey.generate()
        pubkey2 = privkey2.public_key.encode()
        assert len(pubkey2) == 32
        channel_pubkey = res[2].decode("hex")
        channel_box = Box(privkey2, PublicKey(channel_pubkey))
        CIDKey = res[3].decode("hex")

        authenticator = b"ce0:"+pubkey2
        msgE = "".join([seqnum_s,
                        netstring(my_signkey.sign(authenticator)),
                        json.dumps(payload).encode("utf-8"),
                        ])
        msgD = pubkey2 + channel_box.encrypt(msgE, os.urandom(Box.NONCE_SIZE))

        HmsgD = sha256(msgD).digest()
        CIDToken = HKDF(IKM=CIDKey+seqnum_s, dkLen=32,
                        info=b"petmail.org/v1/CIDToken")
        sb = SecretBox(CIDKey)
        CIDBox = sb.encrypt(seqnum_s+HmsgD+channel_pubkey,
                            os.urandom(sb.NONCE_SIZE))

        msgC = "".join([b"c0:",
                        CIDToken,
                        netstring(CIDBox),
                        msgD])

        # now wrap msgC into a msgA for each transport they're using
        self.sendMsgC(msgC)

    def sendMsgC(self, msgC):
        c = self.db.cursor()
        c.execute("SELECT their_STID, their_mailbox_descriptor,"
                  " FROM addressbook WHERE id=?", (self.cid,))
        res = c.fetchone()
        assert res, "missing cid"
        STID = bytes(res[0])
        mbox = json.loads(res[1])
        MSTID = rrid.rerandomize(STID)
        msgB = MSTID + msgC

        privkey1 = PrivateKey.generate()
        pubkey1 = privkey1.public_key.encode()
        assert len(pubkey1) == 32
        transport_pubkey = mbox["transport_pubkey"].decode("hex")
        transport_box = Box(privkey1, PublicKey(transport_pubkey))

        msgA = pubkey1 + transport_box.encrypt(msgB, os.urandom(Box.NONCE_SIZE))

        self.sendMsgA(msgA)

    def sendMsgA(self, msgA):
        # TODO: send msgA over the network
        pass
