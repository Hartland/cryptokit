from hashlib import sha256
from struct import pack
from collections import namedtuple
from binascii import hexlify
from . import BitcoinEncoding


""" Previous hash needs to be given as a byte array in little endian.
script_sig is a byte string. Others are simply integers. """
Input = namedtuple('Input',
                   ['prevout_hash', 'prevout_idx', 'script_sig', 'seqno'])
""" script_pub_key is a byte string. Amount is an integer. """
Output = namedtuple('Output', ['amount', 'script_pub_key'])


class Transaction(BitcoinEncoding):
    """ An object wrapper for a bitcoin transaction. More information on the
    raw format at https://en.bitcoin.it/wiki/Transactions """
    _nullprev = b'\0' * 32

    def __init__(self, raw=None):
        # raw transaction data in byte format
        self._raw = raw
        self.inputs = []
        self.outputs = []
        self.locktime = 0
        self.fees = None
        self.version = 1
        if raw:
            self.disassemble()
        else:
            self._hash = None

    def disassemble(self, raw=None, dump_raw=False, fees=None):
        """ Unpacks a raw transaction into its object components. If raw
        is passed here it will set the raw contents of the object before
        disassembly. Dump raw will mark the raw data for garbage collection
        to save memory. """
        if fees:
            self.fees = fees
        if raw:
            self._raw = raw
        data = self._raw

        # first four bytes, little endian unpack
        self.version = self.funpack('<L', data[:4])

        # decode the number of inputs and adjust position counter
        input_count, data = self.varlen_decode(data[4:])

        # loop over the inputs and parse them out
        self.inputs = []
        for i in range(input_count):
            # get the previous transaction hash and it's output index in the
            # previous transaction
            prevout_hash = data[:32]
            prevout_idx = self.funpack('<L', data[32:36])
            # get length of the txn script
            ss_len, data = self.varlen_decode(data[36:])
            script_sig = data[:ss_len]  # get the script
            # get the sequence number
            seqno = self.funpack('<L', data[ss_len:ss_len + 4])

            # chop off the this transaction from the data for next iteration
            # parsing
            data = data[ss_len + 4:]

            # save the input in the object
            self.inputs.append(
                Input(prevout_hash, prevout_idx, script_sig, seqno))

        output_count, data = self.varlen_decode(data)
        self.outputs = []
        for i in range(output_count):
            amount = self.funpack('<Q', data[:8])
            # length of scriptPubKey, parse out
            ps_len, data = self.varlen_decode(data[8:])
            pk_script = data[:ps_len]
            data = data[ps_len:]
            self.outputs.append(
                Output(amount, pk_script))

        self.locktime = self.funpack('<L', data[:4])
        # reset hash to be recacluated on next grab
        self._hash = None
        # ensure no trailing data...
        assert len(data) == 4
        if dump_raw:
            self._raw = None

        return self

    @property
    def is_coinbase(self):
        """ Is the only input from a null prev address, indicating coinbase?
        Technically we could do more checks, but I believe bitcoind doesn't
        check more than the first input being null to count it as a coinbase
        transaction. """
        return self.inputs[0].prevout_hash == self._nullprev

    def assemble(self):
        """ Reverse of disassemble, pack up the object into a byte string raw
        transaction. """
        data = pack('<L', self.version)

        data += self.varlen_encode(len(self.inputs))
        for prevout_hash, prevout_idx, script_sig, seqno in self.inputs:
            data += prevout_hash
            data += pack('<L', prevout_idx)
            data += self.varlen_encode(len(script_sig))
            data += script_sig
            data += pack('<L', seqno)

        data += self.varlen_encode(len(self.outputs))
        for amount, script_pub_key in self.outputs:
            data += pack('<Q', amount)
            data += self.varlen_encode(len(script_pub_key))
            data += script_pub_key

        data += pack('<L', self.locktime)

        self._raw = data
        # reset hash to be recacluated on next grab
        self._hash = None
        return data

    @property
    def raw(self):
        if self._raw is None:
            self.assemble()
        return self._raw

    @property
    def hash(self):
        """ Compute the hash of the transaction when needed """
        if self._hash is None:
            self._hash = sha256(sha256(self._raw).digest()).digest()
        return self._hash

    @property
    def lehexhash(self):
        return hexlify(self.hash[::-1])

    @property
    def behexhash(self):
        return hexlify(self.hash)

    def to_dict(self):
        return {'inputs': [{'prevout_hash': hexlify(inp[0]),
                            'prevout_idx': inp[1],
                            'script_sig': hexlify(inp[2]),
                            'seqno': inp[3]} for inp in self.inputs],
                 'outputs': [{'amount': out[0],
                              'script_pub_key': hexlify(out[1])}
                               for out in self.outputs],
                'data': hexlify(self._raw),
                'locktime': self.locktime,
                'version': self.version,
                'hash': self.lehexhash}
