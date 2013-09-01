import os
from ... import rrid
from ...netstring import netstring
from nacl.public import PrivateKey, PublicKey, Box

# msgA:
#  a0:
#  pubkey1 [fixed-length]
#  enc(to=transport, from=key1, msgB)
# msgB:
#  netstring(MSTID)
#  msgC

def createMsgA(trec, msgC):
    MSTID = rrid.randomize(trec["STID"].decode("hex"))
    msgB = netstring(MSTID) + msgC

    privkey1 = PrivateKey.generate()
    pubkey1 = privkey1.public_key.encode()
    assert len(pubkey1) == 32
    transport_pubkey = trec["transport_pubkey"].decode("hex")
    transport_box = Box(privkey1, PublicKey(transport_pubkey))

    msgA = b"".join([b"a0:",
                     pubkey1,
                     transport_box.encrypt(msgB, os.urandom(Box.NONCE_SIZE))])
    return msgA
