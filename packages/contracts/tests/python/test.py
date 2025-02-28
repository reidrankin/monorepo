import unittest
from unittest import TestCase, main
from ethereum.utils import decode_hex, encode_hex
from ethereum.tools import tester as t
#from ethereum.tools.tester import TransactionFailed, ABIContract

from eth_tester.exceptions import TransactionFailed


from ethereum.tools import keys
from ethereum.abi import ContractTranslator
import time
from sha3 import keccak_256
from hashlib import sha256

import eth.exceptions

from web3.providers.eth_tester import EthereumTesterProvider
from web3 import Web3

import json
import bitcoin
import os

import time

from eth_tester import EthereumTester, PyEVMBackend

# Command-line flag to skip tests we're not working on
WORKING_ONLY = os.environ.get('WORKING_ONLY', False)
REALITIO_CONTRACT = os.environ.get('REALITIO', 'Realitio')
CLAIM_FEE = int(os.environ.get('CLAIM_FEE', 0))

DEPLOY_GAS = 4500000

QINDEX_CONTENT_HASH = 0
QINDEX_ARBITRATOR = 1
QINDEX_OPENING_TS = 2
QINDEX_STEP_DELAY = 3
QINDEX_FINALIZATION_TS = 4
QINDEX_IS_PENDING_ARBITRATION = 5
QINDEX_BOUNTY = 6
QINDEX_BEST_ANSWER = 7
QINDEX_HISTORY_HASH = 8
QINDEX_BOND = 9

def calculate_answer_hash(answer, nonce):
    if answer[:2] == "0x":
        raise Exception("hash functions expect bytes for bytes32 parameters")
    if not isinstance(nonce, int):
        raise Exception("hash functions expect int for uint256 parameters")
    return "0x"+encode_hex(bytes(Web3.solidityKeccak(['bytes32', 'uint256'], [answer, nonce])))

def calculate_commitment_id(question_id, answer_hash, bond):
    if question_id[:2] == "0x":
        raise Exception("hash functions expect bytes for bytes32 parameters")
    if answer_hash[:2] == "0x":
        raise Exception("hash functions expect bytes for bytes32 parameters")
    if not isinstance(bond, int):
        raise Exception("hash functions expect int for uint256 parameters")
    #return decode_hex(keccak_256(question_id + answer_hash + decode_hex(hex(bond)[2:].zfill(64))).hexdigest())
    return "0x"+encode_hex(bytes(Web3.solidityKeccak(['bytes32', 'bytes32', 'uint256'], [question_id, answer_hash, bond])))

def calculate_content_hash(template_id, question_str, opening_ts):
    return "0x"+encode_hex(bytes(Web3.solidityKeccak(['uint256', 'uint32', 'string'], [template_id, opening_ts, question_str])))

def calculate_question_id(template_id, question_str, arbitrator, timeout, opening_ts, nonce, sender):
    content_hash = calculate_content_hash(template_id, question_str, opening_ts)
    return "0x"+encode_hex(bytes(Web3.solidityKeccak(['bytes32', 'address', 'uint32', 'address', 'uint256'], [content_hash, arbitrator, timeout, sender, nonce])))

def calculate_history_hash(last_history_hash, answer_or_commitment_id, bond, answerer, is_commitment):
    return "0x"+encode_hex(bytes(Web3.solidityKeccak(['bytes32', 'bytes32', 'uint256', 'address', 'bool'], [last_history_hash, answer_or_commitment_id, bond, answerer, is_commitment])))

def from_question_for_contract(txt):
    return txt

def to_answer_for_contract(txt):
    # to_answer_for_contract(("my answer")),
    return decode_hex(hex(txt)[2:].zfill(64))

def from_answer_for_contract(txt):
    return int(encode_hex(txt), 16)

def subfee(bond):
    if CLAIM_FEE == 0:
        return bond
    else:
        fee = CLAIM_FEE
        return int(bond - int(bond/fee))

class TestRealitio(TestCase):

    def assertZeroStatus(self, txid, msg=None):
        self.assertEqual(self.web3.eth.getTransactionReceipt(txid)['status'], 0, msg)

    # Sometimes we seem to get a zero status receipt with no exception raised
    # Not sure if this is what's supposed to happen, but call this in the with block to make sure we get an exception 
    def raiseOnZeroStatus(self, txid):
        if self.web3.eth.getTransactionReceipt(txid)['status'] == 0:
            #print(self.web3.eth.getTransactionReceipt(txid))
            raise TransactionFailed

    def _block_timestamp(self):
        return self.web3.provider.ethereum_tester.get_block_by_number('pending')['timestamp']


    def _advance_clock(self, secs):
        ts = self._block_timestamp()
        self.web3.provider.ethereum_tester.time_travel(ts+secs)
        ts2 = self._block_timestamp()
        self.web3.testing.mine()
        self.assertNotEqual(ts, ts2)

    def _txargs(self, val=0, gas=None, sender=None):
        standard_tx = self.standard_tx

        standard_tx['value'] = val

        if gas is not None:
            standard_tx['gas'] = gas

        if sender is None:
            standard_tx['from'] = self.web3.eth.accounts[0]
        else:
            standard_tx['from'] = sender

        return standard_tx

    def _contractFromBuildJSON(self, con_name, sender=None, startgas=DEPLOY_GAS):

        if sender is None:
            sender = t.k0

        contract_json = {}
        json_fname = con_name + '.json'
        with open('../../truffle/build/contracts/'+json_fname) as f:
            contract_json = f.read()
            f.close()

        bcode = json.loads(contract_json)['bytecode']
        contract_if = json.loads(contract_json)['abi']

        tx_hash = self.web3.eth.contract(abi=contract_if, bytecode=bcode).constructor().transact(self.deploy_tx)
        addr = self.web3.eth.getTransactionReceipt(tx_hash).get('contractAddress')
        return self.web3.eth.contract(addr, abi=contract_if)

    def testS(self):
        return

    def setUp(self):

        genesis_overrides = {'gas_limit': 9000000}
        genesis_params = PyEVMBackend._generate_genesis_params(overrides=genesis_overrides)

        prov = EthereumTesterProvider(EthereumTester(PyEVMBackend(genesis_params)))
        self.web3 = Web3(prov)
        self.web3.testing.mine()

        self.deploy_tx = {
            'from': self.web3.eth.accounts[0],
            'gas': DEPLOY_GAS
        }

        self.standard_tx = {
            'from': self.web3.eth.accounts[0],
            'gas': 200000
        }


        self.arb0 = self._contractFromBuildJSON('RegisteredWalletArbitrator')
        tx_hash = self.arb0.functions.setDisputeFee(10000000000000000).transact(self.standard_tx)
        self.assertIsNotNone(tx_hash)

        fee = self.arb0.functions.getDisputeFee(decode_hex("0x00")).call()
        self.assertEqual(fee, 10000000000000000) 
            
        self.rc0 = self._contractFromBuildJSON(REALITIO_CONTRACT)
        txid = self.arb0.functions.setRealitio(self.rc0.address).transact(self.standard_tx)

        txid = self.arb0.functions.setQuestionFee(100).transact(self.standard_tx)

        expected_question_id = calculate_question_id(0, "my question", self.arb0.address, 30, 0, 0, self.web3.eth.accounts[0])
        
        txid = self.rc0.functions.askQuestion(
            0,
            "my question",
            self.arb0.address,
            30,
            0,
            0
        ).transact(self._txargs(val=1100))
        txr = self.web3.eth.getTransactionReceipt(txid)

        expected_content_hash = calculate_content_hash(0, "my question", 0)

        question = self.rc0.functions.questions(expected_question_id).call()

        ch = "0x" + encode_hex(question[QINDEX_CONTENT_HASH])
        self.assertEqual(expected_content_hash, ch)

        self.assertEqual(int(question[QINDEX_FINALIZATION_TS]), 0)
        self.assertEqual(question[QINDEX_ARBITRATOR], self.arb0.address)

        self.assertEqual(question[QINDEX_STEP_DELAY], 30)
        #self.assertEqual(question[QINDEX_CONTENT_HASH], to_question_for_contract(("my question")))
        self.assertEqual(question[QINDEX_BOUNTY], 1000)

        self.question_id = expected_question_id

    @unittest.skipIf(WORKING_ONLY, "Not under construction")
    def test_fund_increase(self):

        question = self.rc0.functions.questions(self.question_id).call()
        self.assertEqual(question[QINDEX_BOUNTY], 1000)

        txargs = self.standard_tx
        txargs['value'] = 500
        self.rc0.functions.fundAnswerBounty(self.question_id).transact(txargs)

        question = self.rc0.functions.questions(self.question_id).call()
        self.assertEqual(question[QINDEX_BOUNTY], 1500)

    @unittest.skipIf(WORKING_ONLY, "Not under construction")
    def test_no_response_finalization(self):
        # Should not be final if too soon
        self.assertFalse(self.rc0.functions.isFinalized(self.question_id).call())

        self._advance_clock(33)
        
        # Should not be final if there is no answer
        self.assertFalse(self.rc0.functions.isFinalized(self.question_id).call())

        return

    @unittest.skipIf(WORKING_ONLY, "Not under construction")
    def test_simple_response_finalization(self):

        self.rc0.functions.submitAnswer(self.question_id, to_answer_for_contract(12345), 0).transact(self._txargs(val=1))

        self._advance_clock(33)

        best_answer = self.rc0.functions.questions(self.question_id).call()[QINDEX_BEST_ANSWER]
        self.assertEqual(12345, from_answer_for_contract(best_answer))

        self.assertTrue(self.rc0.functions.isFinalized(self.question_id).call())

        self.assertEqual(from_answer_for_contract(self.rc0.functions.getFinalAnswer(self.question_id).call()), 12345)

    @unittest.skipIf(WORKING_ONLY, "Not under construction")
    def test_content_hash(self):
        expect_ch = calculate_content_hash(0, "my question", 0)
        ch = "0x" + encode_hex(self.rc0.functions.questions(self.question_id).call()[QINDEX_CONTENT_HASH])
        self.assertEqual(expect_ch, ch)

    @unittest.skipIf(WORKING_ONLY, "Not under construction")
    def test_get_final_answer_if_match(self):

        expect_ch = calculate_content_hash(0, "my question", 0)
        wrong_ch = calculate_content_hash(0, "not my question", 0)

        self.rc0.functions.submitAnswer(self.question_id, to_answer_for_contract(12345), 0).transact(self._txargs(val=1) )

        # Not finalized yet
        with self.assertRaises(TransactionFailed):
            ans = self.rc0.functions.getFinalAnswerIfMatches(
                self.question_id,
                decode_hex(expect_ch[2:]),
                self.arb0.address,
                0,
                25
            ).call()

        self._advance_clock(33)

        with self.assertRaises(TransactionFailed):
            self.rc0.functions.getFinalAnswerIfMatches(
                self.question_id,
                decode_hex(expect_ch[2:]),
                keys.privtoaddr(t.k2),
                0,
                25
            ).call()

        with self.assertRaises(TransactionFailed):
            self.rc0.functions.getFinalAnswerIfMatches(
                self.question_id,
                decode_hex(wrong_ch[2:]),
                self.arb0.address,
                0,
                25
            ).call()

        with self.assertRaises(TransactionFailed):
            self.rc0.functions.getFinalAnswerIfMatches(
                self.question_id,
                decode_hex(expect_ch[2:]),
                self.arb0.address,
                25,
                99999999999
            ).call()

        with self.assertRaises(TransactionFailed):
            self.rc0.functions.getFinalAnswerIfMatches(
                self.question_id,
                decode_hex(expect_ch[2:]),
                self.arb0.address,
                1893459661, # 2030-01-01
                25
            ).call()

        ans = self.rc0.functions.getFinalAnswerIfMatches(
            self.question_id,
            decode_hex(expect_ch[2:]),
            self.arb0.address,
            0,
            0
        ).call()
        self.assertEqual(from_answer_for_contract(ans), 12345)


    @unittest.skipIf(WORKING_ONLY, "Not under construction")
    def test_earliest_finalization_ts(self):

        self.rc0.functions.submitAnswer(self.question_id, to_answer_for_contract(54321), 0).transact(self._txargs(val=10))
        ts1 = self.rc0.functions.questions(self.question_id).call()[QINDEX_FINALIZATION_TS]
        self.assertEqual(self.rc0.functions.questions(self.question_id).call()[QINDEX_BOND], 10)

        self._advance_clock(1)

        self.rc0.functions.submitAnswer(self.question_id, to_answer_for_contract(54321), 0).transact(self._txargs(val=20))
        self.assertEqual(self.rc0.functions.questions(self.question_id).call()[QINDEX_BOND], 20)
        ts2 = self.rc0.functions.questions(self.question_id).call()[QINDEX_FINALIZATION_TS]

        self.assertTrue(ts2 > ts1, "Submitting an answer advances the finalization timestamp") 

    @unittest.skipIf(WORKING_ONLY, "Not under construction")
    def test_conflicting_response_finalization(self):

        self.rc0.functions.submitAnswer(self.question_id, to_answer_for_contract(12345), 0).transact(self._txargs(val=1)) 
        self.rc0.functions.submitAnswer(self.question_id, to_answer_for_contract(54321), 0).transact(self._txargs(val=10))

        self._advance_clock(33)

        self.assertTrue(self.rc0.functions.isFinalized(self.question_id).call())
        self.assertEqual(from_answer_for_contract(self.rc0.functions.getFinalAnswer(self.question_id).call()), 54321)

    @unittest.skipIf(WORKING_ONLY, "Not under construction")
    def test_arbitrator_answering_answered(self):

        self.rc0.functions.submitAnswer(self.question_id, to_answer_for_contract(12345), 0).transact(self._txargs(val=1))

        # The arbitrator cannot submit an answer that has not been requested. 
        # (If they really want to do this, they can always pay themselves for arbitration.)
        with self.assertRaises(TransactionFailed):
            self.arb0.functions.submitAnswerByArbitrator(self.question_id, to_answer_for_contract(123456), keys.privtoaddr(t.k0)).transact() 

        # You cannot notify realitio of arbitration unless you are the arbitrator
        with self.assertRaises(TransactionFailed):
            self.rc0.functions.notifyOfArbitrationRequest(self.question_id, keys.privtoaddr(t.k0), 0).transact() 

        self.assertFalse(self.rc0.functions.isFinalized(self.question_id).call())

        fee = self.arb0.functions.getDisputeFee(decode_hex("0x00")).call()
        self.assertTrue(self.arb0.functions.requestArbitration(self.question_id, 0).transact(self._txargs(val=fee)), "Requested arbitration")
        question = self.rc0.functions.questions(self.question_id).call()
        self.assertTrue(question[QINDEX_IS_PENDING_ARBITRATION], "When arbitration is pending for an answered question, we set the is_pending_arbitration flag to True")
        self.arb0.functions.submitAnswerByArbitrator(self.question_id, to_answer_for_contract(123456), keys.privtoaddr(t.k0)).transact()

        self.assertTrue(self.rc0.functions.isFinalized(self.question_id).call())
        self.assertEqual(from_answer_for_contract(self.rc0.functions.getFinalAnswer(self.question_id).call()), 123456, "Arbitrator submitting final answer calls finalize")

        self.assertNotEqual(self.rc0.functions.questions(self.question_id).call()[QINDEX_BOND], 0)

    @unittest.skipIf(WORKING_ONLY, "Not under construction")
    def test_arbitrator_answering_assigning_answerer_right(self):

        if REALITIO_CONTRACT != 'Realitio_v2_1':
            print("Skipping test_arbitrator_answering_assigning_answerer_right, not a feature of this contract")
            return

        k2 = self.web3.eth.accounts[2]
        k3 = self.web3.eth.accounts[3]
        k4 = self.web3.eth.accounts[4]
        st = None
        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1001, 0, 2, k4)
        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1002, 2, 4, k3)
        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1002, 4, 8, k3)

        last_hash = self.rc0.functions.questions(self.question_id).call()[QINDEX_HISTORY_HASH]

        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1001, 8, 16, k4)

        fee = self.arb0.functions.getDisputeFee(decode_hex("0x00")).call()
        self.assertTrue(self.arb0.functions.requestArbitration(self.question_id, 0).transact(self._txargs(val=fee)), "Requested arbitration")

        arb_answer = to_answer_for_contract(1001)
        arb_payer = keys.privtoaddr(t.k2)

        hist_hash = self.rc0.functions.questions(self.question_id).call()[QINDEX_HISTORY_HASH]

        # Only the arbitrator can do this
        with self.assertRaises(TransactionFailed):
            self.rc0.functions.assignWinnerAndSubmitAnswerByArbitrator(self.question_id, arb_answer, arb_payer, st['hash'][0], st['answer'][0], st['addr'][0] ).transact() 

        self.arb0.functions.assignWinnerAndSubmitAnswerByArbitrator(self.question_id, arb_answer, arb_payer, st['hash'][0], st['answer'][0], st['addr'][0] ).transact() 

        st['hash'].insert(0, hist_hash)
        st['bond'].insert(0, 0)
        st['answer'].insert(0, arb_answer)
        st['addr'].insert(0, k4)

        self.rc0.functions.claimWinnings(self.question_id, st['hash'], st['addr'], st['bond'], st['answer']).transact()
        self.assertEqual(self.rc0.functions.balanceOf(k4).call(), 2+subfee(4)+subfee(8)+subfee(16)+1000, "The last answerer gets it all for a right answer")


    @unittest.skipIf(WORKING_ONLY, "Not under construction")
    def test_arbitrator_answering_assigning_answerer_right_commit(self):

        if REALITIO_CONTRACT != 'Realitio_v2_1':
            print("Skipping test_arbitrator_answering_assigning_answerer_right_commit, not a feature of this contract")
            return

        k2 = self.web3.eth.accounts[2]
        k3 = self.web3.eth.accounts[3]
        k4 = self.web3.eth.accounts[4]
        st = None
        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1001, 0, 2, k4)
        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1002, 2, 4, k3)
        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1002, 4, 8, k3)

        last_hash = self.rc0.functions.questions(self.question_id).call()[QINDEX_HISTORY_HASH]

        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1001, 8, 16, k4, True)
        nonce = st['nonce'][0]
        self.rc0.functions.submitAnswerReveal( self.question_id, to_answer_for_contract(1001), nonce, 16).transact(self._txargs(sender=k4, val=0))

        fee = self.arb0.functions.getDisputeFee(decode_hex("0x00")).call()
        self.assertTrue(self.arb0.functions.requestArbitration(self.question_id, 0).transact(self._txargs(val=fee)), "Requested arbitration")

        arb_answer = to_answer_for_contract(1001)
        arb_payer = keys.privtoaddr(t.k2)

        hist_hash = self.rc0.functions.questions(self.question_id).call()[QINDEX_HISTORY_HASH]

        self.arb0.functions.assignWinnerAndSubmitAnswerByArbitrator(self.question_id, arb_answer, arb_payer, st['hash'][0], st['answer'][0], st['addr'][0] ).transact() 

        st['hash'].insert(0, hist_hash)
        st['bond'].insert(0, 0)
        st['answer'].insert(0, arb_answer)
        st['addr'].insert(0, k4)

        self.rc0.functions.claimWinnings(self.question_id, st['hash'], st['addr'], st['bond'], st['answer']).transact()
        self.assertEqual(self.rc0.functions.balanceOf(k4).call(), 2+subfee(4)+subfee(8)+subfee(16)+1000, "The last answerer gets it all for a right answer")



    @unittest.skipIf(WORKING_ONLY, "Not under construction")
    def test_arbitrator_answering_assigning_answerer_wrong_commit(self):

        if REALITIO_CONTRACT != 'Realitio_v2_1':
            print("Skipping test_arbitrator_answering_assigning_answerer_wrong_commit, not a feature of this contract")
            return

        k2 = self.web3.eth.accounts[2]
        k3 = self.web3.eth.accounts[3]
        k4 = self.web3.eth.accounts[4]
        st = None
        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1001, 0, 2, k4)
        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1002, 2, 4, k3)
        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1002, 4, 8, k3)

        last_hash = self.rc0.functions.questions(self.question_id).call()[QINDEX_HISTORY_HASH]

        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1001, 8, 16, k4, True)
        nonce = st['nonce'][0]
        self.rc0.functions.submitAnswerReveal( self.question_id, to_answer_for_contract(1001), nonce, 16).transact(self._txargs(sender=k4, val=0))

        fee = self.arb0.functions.getDisputeFee(decode_hex("0x00")).call()
        self.assertTrue(self.arb0.functions.requestArbitration(self.question_id, 0).transact(self._txargs(val=fee)), "Requested arbitration")

        arb_answer = to_answer_for_contract(98765)
        arb_payer = keys.privtoaddr(t.k2)

        hist_hash = self.rc0.functions.questions(self.question_id).call()[QINDEX_HISTORY_HASH]

        self.arb0.functions.assignWinnerAndSubmitAnswerByArbitrator(self.question_id, arb_answer, arb_payer, st['hash'][0], st['answer'][0], st['addr'][0] ).transact() 

        st['hash'].insert(0, hist_hash)
        st['bond'].insert(0, 0)
        st['answer'].insert(0, arb_answer)
        st['addr'].insert(0, arb_payer)

        self.rc0.functions.claimWinnings(self.question_id, st['hash'], st['addr'], st['bond'], st['answer']).transact()
        self.assertEqual(self.rc0.functions.balanceOf(arb_payer).call(), 2+subfee(4)+subfee(8)+subfee(16)+1000, "The last answerer gets it all for a right answer")


    @unittest.skipIf(WORKING_ONLY, "Not under construction")
    def test_arbitrator_answering_assigning_answerer_wrong(self):

        if REALITIO_CONTRACT != 'Realitio_v2_1':
            print("Skipping test_arbitrator_answering_assigning_answerer_wrong, not a feature of this contract")
            return

        k2 = self.web3.eth.accounts[2]
        k3 = self.web3.eth.accounts[3]
        k4 = self.web3.eth.accounts[4]
        st = None
        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1001, 0, 2, k4)
        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1002, 2, 4, k3)
        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1002, 4, 8, k3)

        last_hash = self.rc0.functions.questions(self.question_id).call()[QINDEX_HISTORY_HASH]

        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1001, 8, 16, k4)

        fee = self.arb0.functions.getDisputeFee(decode_hex("0x00")).call()
        self.assertTrue(self.arb0.functions.requestArbitration(self.question_id, 0).transact(self._txargs(val=fee)), "Requested arbitration")

        arb_answer = to_answer_for_contract(123456)
        arb_payer = keys.privtoaddr(t.k2)

        hist_hash = self.rc0.functions.questions(self.question_id).call()[QINDEX_HISTORY_HASH]

        self.arb0.functions.assignWinnerAndSubmitAnswerByArbitrator(self.question_id, arb_answer, arb_payer, st['hash'][0], st['answer'][0], st['addr'][0] ).transact() 

        st['hash'].insert(0, hist_hash)
        st['bond'].insert(0, 0)
        st['answer'].insert(0, arb_answer)
        st['addr'].insert(0, arb_payer)

        self.rc0.functions.claimWinnings(self.question_id, st['hash'], st['addr'], st['bond'], st['answer']).transact()
        self.assertEqual(self.rc0.functions.balanceOf(arb_payer).call(), 2+subfee(4)+subfee(8)+subfee(16)+1000, "The arb payer gets it all for a wrong answer")


    @unittest.skipIf(WORKING_ONLY, "Not under construction")
    def test_arbitrator_answering_assigning_answerer_unrevealed_commit(self):

        if REALITIO_CONTRACT != 'Realitio_v2_1':
            print("Skipping test_arbitrator_answering_assigning_answerer_unrevealed_commit, not a feature of this contract")
            return

        k2 = self.web3.eth.accounts[2]
        k3 = self.web3.eth.accounts[3]
        k4 = self.web3.eth.accounts[4]
        st = None
        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1001, 0, 2, k4)
        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1002, 2, 4, k3)
        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1002, 4, 8, k3)

        last_hash = self.rc0.functions.questions(self.question_id).call()[QINDEX_HISTORY_HASH]

        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 0, 8, 16, k4, True)

        fee = self.arb0.functions.getDisputeFee(decode_hex("0x00")).call()
        self.assertTrue(self.arb0.functions.requestArbitration(self.question_id, 0).transact(self._txargs(val=fee)), "Requested arbitration")

        arb_answer = to_answer_for_contract(0)
        arb_payer = keys.privtoaddr(t.k2)

        ##self.rc0.functions.claimWinnings(self.question_id, st['hash'], st['addr'], st['bond'], st['answer']).transact()
        self.assertEqual(st['answer'][-1], to_answer_for_contract(1001))
        hist_hash = self.rc0.functions.questions(self.question_id).call()[QINDEX_HISTORY_HASH]

        # Arbitration fails if the reveal timeout has not come yet
        with self.assertRaises(TransactionFailed):
            self.arb0.functions.assignWinnerAndSubmitAnswerByArbitrator(self.question_id, arb_answer, arb_payer, st['hash'][0], st['answer'][0], st['addr'][0] ).transact() 

        self._advance_clock(10)
        self.arb0.functions.assignWinnerAndSubmitAnswerByArbitrator(self.question_id, arb_answer, arb_payer, st['hash'][0], st['answer'][0], st['addr'][0] ).transact() 

        st['hash'].insert(0, hist_hash)
        st['bond'].insert(0, 0)
        st['answer'].insert(0, arb_answer)
        st['addr'].insert(0, arb_payer)

        self.rc0.functions.claimWinnings(self.question_id, st['hash'], st['addr'], st['bond'], st['answer']).transact()
        self.assertEqual(self.rc0.functions.balanceOf(arb_payer).call(), 2+subfee(4)+subfee(8)+subfee(16)+1000, "The arb payer gets it all for a wrong answer")


        return

        # The arbitrator cannot submit an answer that has not been requested. 
        # (If they really want to do this, they can always pay themselves for arbitration.)
        with self.assertRaises(TransactionFailed):
            self.arb0.functions.assignWinnerAndSubmitAnswerByArbitrator(self.question_id, to_answer_for_contract(123456), keys.privtoaddr(t.k0)).transact() 

        # You cannot notify realitio of arbitration unless you are the arbitrator
        with self.assertRaises(TransactionFailed):
            self.rc0.functions.notifyOfArbitrationRequest(self.question_id, keys.privtoaddr(t.k0), 0).transact() 

        self.assertFalse(self.rc0.functions.isFinalized(self.question_id).call())

        fee = self.arb0.functions.getDisputeFee(decode_hex("0x00")).call()
        self.assertTrue(self.arb0.functions.requestArbitration(self.question_id, 0).transact(self._txargs(val=fee)), "Requested arbitration")
        question = self.rc0.functions.questions(self.question_id).call()
        #self.assertEqual(question[QINDEX_FINALIZATION_TS], 1, "When arbitration is pending for an answered question, we set the finalization_ts to 1")
        self.assertTrue(question[QINDEX_IS_PENDING_ARBITRATION], "When arbitration is pending for an answered question, we set the is_pending_arbitration flag to True")
        self.arb0.functions.submitAnswerByArbitrator(self.question_id, to_answer_for_contract(123456), keys.privtoaddr(t.k0)).transact()

        self.assertTrue(self.rc0.functions.isFinalized(self.question_id).call())
        self.assertEqual(from_answer_for_contract(self.rc0.functions.getFinalAnswer(self.question_id).call()), 123456, "Arbitrator submitting final answer calls finalize")

        self.assertNotEqual(self.rc0.functions.questions(self.question_id).call()[QINDEX_BOND], 0)




    @unittest.skipIf(WORKING_ONLY, "Not under construction")
    def test_arbitrator_cancel(self):

        if REALITIO_CONTRACT != 'Realitio_v2_1':
            print("Skipping test_arbitrator_cancel, not a feature of this contract")
            return

        self.rc0.functions.submitAnswer(self.question_id, to_answer_for_contract(12345), 0).transact(self._txargs(val=1))

        # The arbitrator cannot submit an answer that has not been requested. 
        # (If they really want to do this, they can always pay themselves for arbitration.)
        with self.assertRaises(TransactionFailed):
            self.arb0.functions.submitAnswerByArbitrator(self.question_id, to_answer_for_contract(123456), keys.privtoaddr(t.k0)).transact() 

        # The arbitrator cannot cancel arbitration that has not been requested
        with self.assertRaises(TransactionFailed):
            self.arb0.functions.cancelArbitration(self.question_id).transact()

        self.assertFalse(self.rc0.functions.isFinalized(self.question_id).call())

        fee = self.arb0.functions.getDisputeFee(decode_hex("0x00")).call()
        self.assertTrue(self.arb0.functions.requestArbitration(self.question_id, 0).transact(self._txargs(val=fee)), "Requested arbitration")
        question = self.rc0.functions.questions(self.question_id).call()
        #self.assertEqual(question[QINDEX_FINALIZATION_TS], 1, "When arbitration is pending for an answered question, we set the finalization_ts to 1")
        self.assertTrue(question[QINDEX_IS_PENDING_ARBITRATION], "When arbitration is pending for an answered question, we set the is_pending_arbitration flag to True")

        # Only the arbitrator can cancel arbitration
        with self.assertRaises(TransactionFailed):
            self.rc0.functions.cancelArbitration(self.question_id).transact()
        
        cancelled_ts = self._block_timestamp()
        self.arb0.functions.cancelArbitration(self.question_id).transact();
        question = self.rc0.functions.questions(self.question_id).call()

        self.assertFalse(self.rc0.functions.isFinalized(self.question_id).call())

        # The arbitrator cannot cancel arbitration again as it is no longer pending arbitratin
        with self.assertRaises(TransactionFailed):
            self.arb0.functions.cancelArbitration(self.question_id).transact()

        self.assertFalse(question[QINDEX_IS_PENDING_ARBITRATION], "When arbitration has been cancelled, is_pending_arbitration flag is set back to False")
        self.assertEqual(question[QINDEX_FINALIZATION_TS], cancelled_ts + 30, "Cancelling arbitration extends the timeout")

        # You can submit answers again
        self.rc0.functions.submitAnswer(self.question_id, to_answer_for_contract(54321), 0).transact(self._txargs(val=2))

        # You can request arbitration again
        self.assertTrue(self.arb0.functions.requestArbitration(self.question_id, 0).transact(self._txargs(val=fee)), "Requested arbitration again")


    @unittest.skipIf(WORKING_ONLY, "Not under construction")
    def test_arbitrator_answering_unanswered(self):

        with self.assertRaises(TransactionFailed):
            self.arb0.functions.submitAnswerByArbitrator(self.question_id, to_answer_for_contract(123456), self.arb0.address).transact() 

        self.assertFalse(self.rc0.functions.isFinalized(self.question_id).call())
        self.assertEqual(self.rc0.functions.questions(self.question_id).call()[QINDEX_BOND], 0)

        fee = self.arb0.functions.getDisputeFee(decode_hex("0x00")).call()

        # TODO: This doesn't do anything, which is OK, but why doesn't it raise a TransactionFailed??
        #with self.assertRaises(TransactionFailed):
        self.arb0.functions.requestArbitration(self.question_id, 0).transact(self._txargs(val=fee))

        self.assertFalse(self.rc0.functions.questions(self.question_id).call()[QINDEX_IS_PENDING_ARBITRATION])

    def submitAnswerReturnUpdatedState(self, st, qid, ans, max_last, bond, sdr, is_commitment = False, is_arbitrator = False, skip_sender = False):
        if st is None:
            st = {
                'addr': [],
                'bond': [],
                'answer': [],
                'hash': [],
                'nonce': [], # only for commitments
            }
        hist_hash = self.rc0.functions.questions(qid).call()[QINDEX_HISTORY_HASH]
        st['hash'].insert(0, hist_hash)
        st['bond'].insert(0, bond)
        st['answer'].insert(0, to_answer_for_contract(ans))
        st['addr'].insert(0, sdr)
        nonce = None
        NULL_ADDRESS = "0x0000000000000000000000000000000000000000"

        if is_commitment:
            nonce = 1234
            answer_hash = calculate_answer_hash(to_answer_for_contract(ans), nonce)
            commitment_id = calculate_commitment_id(decode_hex(self.question_id[2:]), decode_hex(answer_hash[2:]), bond)
            #self.assertEqual(to_answer_for_contract(ans), commitment_id)
            if skip_sender:
                self.rc0.functions.submitAnswerCommitment(qid, decode_hex(answer_hash[2:]), max_last, NULL_ADDRESS).transact(self._txargs(val=bond, sender=sdr))
            else:
                self.rc0.functions.submitAnswerCommitment(qid, decode_hex(answer_hash[2:]), max_last, sdr).transact(self._txargs(val=bond, sender=sdr))
            st['answer'][0] = decode_hex(commitment_id[2:])
        else:
            if is_arbitrator:
                self.arb0.functions.submitAnswerByArbitrator(qid, to_answer_for_contract(ans), 0, 0, sdr).transact(self._txargs(val=bond, sender=sdr))
            else:
                self.rc0.functions.submitAnswer(qid, to_answer_for_contract(ans), max_last).transact(self._txargs(val=bond, sender=sdr))
        st['nonce'].insert(0, nonce)
        return st


    @unittest.skipIf(WORKING_ONLY, "Not under construction")
    def test_bond_claim_same_person_repeating_self(self):
        st = None

        sdr = self.web3.eth.accounts[3]

        ##hist_hash = self.rc0.functions.questions(self.question_id).call()[QINDEX_HISTORY_HASH]
        ##self.assertEqual(hist_hash, '0x0000000000000000000000000000000000000000000000000000000000000000')
        ##st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1001, 0, 2, t.k3)
        ##self.assertEqual(st['hash'][0], hist_hash)
        ##sdr = self.web3.eth.accounts[0]

        ##bond = 1
        ##ans = 0
        ##qid = self.question_id
        ##max_last = 0
        ##self.rc0.functions.submitAnswer(qid, to_answer_for_contract(ans), max_last).transact(self._txargs(val=bond, sender=sdr))
        ##new_hist_hash = "0x"+encode_hex(self.rc0.functions.questions(self.question_id).call()[QINDEX_HISTORY_HASH])
        ##new_hash = calculate_history_hash(hist_hash, to_answer_for_contract(ans), bond, sdr, False)
        ##self.assertEqual(new_hash, new_hist_hash)
        
        ##self._advance_clock(33)
        ##self.rc0.functions.claimWinnings(self.question_id, [hist_hash], [sdr], [bond], [to_answer_for_contract(ans)]).transact()
        ##return

        ##print(st)

        ##self._advance_clock(33)
        ##self.rc0.functions.claimWinnings(self.question_id, st['hash'], st['addr'], st['bond'], st['answer']).transact()
        ##return

        #hist_hash = "0x" + encode_hex(self.rc0.functions.questions(self.question_id).call()[QINDEX_HISTORY_HASH])
        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1001, 0, 20, sdr)
        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1001, 20, 40, sdr)
        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1001, 40, 80, sdr)
        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1001, 80, 160, sdr)
        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1001, 160, 320, sdr)
        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1001, 320, 640, sdr)
        self._advance_clock(33)
        self.rc0.functions.claimWinnings(self.question_id, st['hash'], st['addr'], st['bond'], st['answer']).transact()
        self.assertEqual(self.rc0.functions.balanceOf(sdr).call(), 640+subfee(320)+subfee(160)+subfee(80)+subfee(40)+subfee(20)+1000)

    @unittest.skipIf(WORKING_ONLY, "Not under construction")
    def test_bond_claim_same_person_contradicting_self(self):
        k3 = self.web3.eth.accounts[3]
        st = None
        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1001, 0, 20, k3)
        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1002, 20, 40, k3)
        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1001, 40, 80, k3)
        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1004, 80, 160, k3)
        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1003, 160, 320, k3)
        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1001, 320, 640, k3)
        self._advance_clock(33)
        self.rc0.functions.claimWinnings(self.question_id, st['hash'], st['addr'], st['bond'], st['answer']).transact()
        self.assertEqual(self.rc0.functions.balanceOf(k3).call(), 640+subfee(320)+subfee(160)+subfee(80)+subfee(40)+subfee(20)+1000)

    @unittest.skipIf(WORKING_ONLY, "Not under construction")
    def test_subfee(self):
        if CLAIM_FEE == 0:
            return
        else:
            self.assertEqual(subfee(100), 98)
            self.assertEqual(subfee(1), 1)

    @unittest.skipIf(WORKING_ONLY, "Not under construction")
    def test_set_dispute_fee(self):

        # fee of 0 should mean you can never request arbitration
        self.arb0.functions.setDisputeFee(0).transact()
        with self.assertRaises(TransactionFailed):
            fee = self.arb0.functions.getDisputeFee(decode_hex("0x00")).call()
            txid = self.arb0.functions.requestArbitration(self.question_id, 0).transact(self._txargs(val=fee))
            self.raiseOnZeroStatus(txid)

        self.arb0.functions.setDisputeFee(123).transact()
        self.assertEqual(self.arb0.functions.getDisputeFee(self.question_id).call(), 123)

        # question-specific fee should work for that question
        self.arb0.functions.setCustomDisputeFee(self.question_id, 23).transact()
        self.assertEqual(self.arb0.functions.getDisputeFee(self.question_id).call(), 23)

        # removing custom fee should resurrect the default fee
        self.arb0.functions.setCustomDisputeFee(self.question_id, 0).transact()
        self.assertEqual(self.arb0.functions.getDisputeFee(self.question_id).call(), 123)
        return

    @unittest.skipIf(WORKING_ONLY, "Not under construction")
    def test_arbitration_max_previous(self):
        k3 = self.web3.eth.accounts[3]
        k4 = self.web3.eth.accounts[4]
        st = None
        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1001, 0, 2, k4)
        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1002, 2, 4, k3)
        fee = self.arb0.functions.getDisputeFee(encode_hex("0x00")).call()
        with self.assertRaises(TransactionFailed):
            txid = self.arb0.functions.requestArbitration(self.question_id, 2).transact(self._txargs(val=fee))
            self.raiseOnZeroStatus(txid)
        self.arb0.functions.requestArbitration(self.question_id, 4).transact(self._txargs(val=fee))
        return

    @unittest.skipIf(WORKING_ONLY, "Not under construction")
    def test_bond_claim_arbitration_existing_none(self):
        fee = self.arb0.functions.getDisputeFee(encode_hex("0x00")).call()
        with self.assertRaises(TransactionFailed):
            txid = self.arb0.functions.requestArbitration(self.question_id, 0).transact(self._txargs(val=fee))
            self.raiseOnZeroStatus(txid)
        return

    @unittest.skipIf(WORKING_ONLY, "Not under construction")
    def test_bond_claim_arbitration_existing_final(self):
        fee = self.arb0.functions.getDisputeFee(encode_hex("0x00")).call()
        k3 = self.web3.eth.accounts[3]
        k4 = self.web3.eth.accounts[4]
        st = None
        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1001, 0, 2, k4)
        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1002, 2, 4, k3)
        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1002, 4, 8, k3)
        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1001, 8, 16, k4)

        self.arb0.functions.requestArbitration(self.question_id, 0).transact(self._txargs(val=fee))

        st['hash'].insert(0, self.rc0.functions.questions(self.question_id).call()[QINDEX_HISTORY_HASH])
        st['addr'].insert(0, k4)
        st['bond'].insert(0, 0)
        st['answer'].insert(0, to_answer_for_contract(1001))
        self.arb0.functions.submitAnswerByArbitrator(self.question_id, to_answer_for_contract(1001), k4).transact() 

        self.rc0.functions.claimWinnings(self.question_id, st['hash'], st['addr'], st['bond'], st['answer']).transact()
        self.assertEqual(self.rc0.functions.balanceOf(k4).call(), 16+8+4+2+1000)


    @unittest.skipIf(WORKING_ONLY, "Not under construction")
    def test_bond_claim_split_over_transactions(self):

        k4 = self.web3.eth.accounts[4]

        st = None
        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1001, 0, 2, k4)
        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1002, 2, 4, k4)
        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1002, 4, 8, k4)
        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1001, 8, 16, k4)

        self._advance_clock(33)
        self.rc0.functions.claimWinnings(self.question_id, st['hash'][:2], st['addr'][:2], st['bond'][:2], st['answer'][:2]).transact()
        self.assertEqual(self.rc0.functions.balanceOf(k4).call(), 16+1000)
        self.rc0.functions.claimWinnings(self.question_id, st['hash'][2:], st['addr'][2:], st['bond'][2:], st['answer'][2:]).transact()
        self.assertEqual(self.rc0.functions.balanceOf(k4).call(), 16+8+4+2+1000)

    @unittest.skipIf(WORKING_ONLY, "Not under construction")
    def test_bond_claim_after_reveal_fail(self):

        k3 = self.web3.eth.accounts[3]
        k4 = self.web3.eth.accounts[4]
        k5 = self.web3.eth.accounts[5]
        k6 = self.web3.eth.accounts[6]

        st = None
        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1002,  0,  1, k3, False)
        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1001,  1,  2, k5, False)
        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1003,  2,  4, k4, False) 
        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1002,  4,  8, k6, False)
        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1004,  8, 16, k5, True)
        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1002, 16, 32, k4, True)
    
        self._advance_clock(33)
        self.rc0.functions.claimWinnings(self.question_id, st['hash'], st['addr'], st['bond'], st['answer']).transact()
        self.assertEqual(self.rc0.functions.balanceOf(k6).call(), 32+16+8+4+2-1+1000)
        self.assertEqual(self.rc0.functions.balanceOf(k3).call(), 1+1)

    @unittest.skipIf(WORKING_ONLY, "Not under construction")
    def test_bond_claim_split_over_transactions_payee_later(self):

        k3 = self.web3.eth.accounts[3]
        k4 = self.web3.eth.accounts[4]
        k5 = self.web3.eth.accounts[5]
        k6 = self.web3.eth.accounts[6]

        st = None
        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1002,  0,  1, k3, False)
        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1001,  1,  2, k5, False)
        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1003,  2,  4, k4, False) 
        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1002,  4,  8, k6, False)
        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1004,  8, 16, k5, True)
        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1002, 16, 32, k4, True)

        self._advance_clock(33)
        self.rc0.functions.claimWinnings(self.question_id, st['hash'][:2], st['addr'][:2], st['bond'][:2], st['answer'][:2]).transact()
        self.rc0.functions.claimWinnings(self.question_id, st['hash'][2:], st['addr'][2:], st['bond'][2:], st['answer'][2:]).transact()
        self.assertEqual(self.rc0.functions.balanceOf(k6).call(), 32+16+8+4+2-1+1000)
        self.assertEqual(self.rc0.functions.balanceOf(k3).call(), 1+1)

    @unittest.skipIf(WORKING_ONLY, "Not under construction")
    def test_answer_reveal_calculation(self):
        h = calculate_answer_hash(to_answer_for_contract(1003), 94989)
        self.assertEqual(h, '0x23e796d2bf4f5f890b1242934a636f4802aadd480b6f83c754d2bd5920f78845')

    @unittest.skipIf(WORKING_ONLY, "Not under construction")
    def test_answer_commit_normal(self):

        k3 = self.web3.eth.accounts[3]
        k4 = self.web3.eth.accounts[4]
        k5 = self.web3.eth.accounts[5]
        k6 = self.web3.eth.accounts[6]

        self.web3.testing.mine()
        self.assertEqual(self.rc0.functions.questions(self.question_id).call()[QINDEX_STEP_DELAY], 30)

        st = None
        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1002,  0,  1, k3, True)
        nonce = st['nonce'][0]
        hh = st['hash'][0]
        commitment_id = st['answer'][0]

        comm = self.rc0.functions.commitments(commitment_id).call()
        reveal_ts = comm[0]
        self.assertTrue(reveal_ts > 0)

        self.web3.testing.mine()
        self.assertTrue(reveal_ts > self._block_timestamp())

        with self.assertRaises(TransactionFailed):
            q = self.rc0.functions.getFinalAnswer(self.question_id).call()

        #print(self.rc0.functions.questions(self.question_id).call())
        txid = self.rc0.functions.submitAnswerReveal( self.question_id, to_answer_for_contract(1002), nonce, 1).transact(self._txargs(sender=k3, val=0))

        comm = self.rc0.functions.commitments(commitment_id).call()
        reveal_ts = comm[0]
        is_revealed = comm[1]
        revealed_answer = comm[2]
        self.assertTrue(reveal_ts > 0)
        self.assertTrue(is_revealed)
        self.assertEqual(revealed_answer, to_answer_for_contract(1002))


        self.raiseOnZeroStatus(txid)

        #rcp = self.web3.eth.getTransactionReceipt(txid)
        self._advance_clock(33)
        #time.sleep(10)

        q = self.rc0.functions.questions(self.question_id).call()[QINDEX_BEST_ANSWER]
        self.assertEqual(from_answer_for_contract(q), 1002)

        self.rc0.functions.claimWinnings(self.question_id, st['hash'], st['addr'], st['bond'], st['answer']).transact()
        self.assertEqual(self.rc0.functions.balanceOf(k3).call(), 1001)

    @unittest.skipIf(WORKING_ONLY, "Not under construction")
    def test_answer_commit_skip_sender(self):
        st = None

        k3 = self.web3.eth.accounts[3]
        k4 = self.web3.eth.accounts[4]
        k5 = self.web3.eth.accounts[5]
        k6 = self.web3.eth.accounts[6]

        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1002,  0,  1, k3, True, False, True)
        nonce = st['nonce'][0]
        hh = st['hash'][0]

        with self.assertRaises(TransactionFailed):
            q = self.rc0.functions.getFinalAnswer(self.question_id).call()

        self.rc0.functions.submitAnswerReveal( self.question_id, to_answer_for_contract(1002), nonce, 1).transact(self._txargs(sender=k3, val=0))

        self._advance_clock(33)

        q = self.rc0.functions.getFinalAnswer(self.question_id).call()
        self.assertEqual(from_answer_for_contract(q), 1002)

        self.rc0.functions.claimWinnings(self.question_id, st['hash'], st['addr'], st['bond'], st['answer']).transact()
        self.assertEqual(self.rc0.functions.balanceOf(k3).call(), 1001)

    @unittest.skipIf(WORKING_ONLY, "Not under construction")
    def test_answer_no_answer_no_commit(self):

        k3 = self.web3.eth.accounts[3]

        st = None
        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1002,  0,  1, k3, True)
        nonce = st['nonce'][0]
        hh = st['hash'][0]

        with self.assertRaises(TransactionFailed):
            q = self.rc0.functions.getFinalAnswer(self.question_id).call()

        self.rc0.functions.submitAnswerReveal( self.question_id, to_answer_for_contract(1002), nonce, 1).transact(self._txargs(sender=k3, val=0))
        self._advance_clock(33)

        q = self.rc0.functions.getFinalAnswer(self.question_id).call()
        self.assertEqual(from_answer_for_contract(q), 1002)

        self.rc0.functions.claimWinnings(self.question_id, st['hash'], st['addr'], st['bond'], st['answer']).transact()
        self.assertEqual(self.rc0.functions.balanceOf(k3).call(), 1001)

    @unittest.skipIf(WORKING_ONLY, "Not under construction")
    def test_answer_commit_expired(self):

        k3 = self.web3.eth.accounts[3]

        st = None
        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1002,  0,  1, k3, True)
        nonce = st['nonce'][0]
        hh = st['hash'][0]

        self._advance_clock(5)
        with self.assertRaises(TransactionFailed):
            txid = self.rc0.functions.submitAnswerReveal( self.question_id, to_answer_for_contract(1002), nonce, 1).transact(self._txargs(sender=k3, val=0))
            self.raiseOnZeroStatus(txid)

    @unittest.skipIf(WORKING_ONLY, "Not under construction")
    def test_answer_commit_with_arbitration_pending(self):
    
        k3 = self.web3.eth.accounts[3]
        fee = self.arb0.functions.getDisputeFee(encode_hex("0x00")).call()

        st = None
        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1002,  0,  1, k3, True)
        nonce = st['nonce'][0]
        hh = st['hash'][0]

        self.arb0.functions.requestArbitration(self.question_id, 0).transact(self._txargs(val=fee))

        #with self.assertRaises(TransactionFailed):
        st = self.rc0.functions.submitAnswerReveal( self.question_id, to_answer_for_contract(1002), nonce, 1).transact(self._txargs(sender=k3, val=0))


    @unittest.skipIf(WORKING_ONLY, "Not under construction")
    def test_bond_claim_arbitration_existing_not_final(self):
    
        k3 = self.web3.eth.accounts[3]
        k4 = self.web3.eth.accounts[4]

        fee = self.arb0.functions.getDisputeFee(encode_hex("0x00")).call()

        st = None
        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1001, 0, 2, k4)
        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1002, 2, 4, k3)
        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1002, 4, 8, k3)
        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1001, 8, 16, k4)

        self.arb0.functions.requestArbitration(self.question_id, 0).transact(self._txargs(val=fee))

        st['hash'].insert(0, self.rc0.functions.questions(self.question_id).call()[QINDEX_HISTORY_HASH])
        st['addr'].insert(0, k3)
        st['bond'].insert(0, 0)
        st['answer'].insert(0, to_answer_for_contract(1002))
        self.arb0.functions.submitAnswerByArbitrator(self.question_id, to_answer_for_contract(1002), k3).transact(self._txargs(val=0)) 

        self.rc0.functions.claimWinnings(self.question_id, st['hash'], st['addr'], st['bond'], st['answer']).transact()
        self.assertEqual(self.rc0.functions.balanceOf(k3).call(), 16+8+4+2+1000)


    @unittest.skipIf(WORKING_ONLY, "Not under construction")
    def test_min_payment_with_bond_param(self):

        k3 = self.web3.eth.accounts[3]
        k4 = self.web3.eth.accounts[4]
        k5 = self.web3.eth.accounts[5]

        self.rc0.functions.submitAnswer(self.question_id, to_answer_for_contract(12345), 0).transact(self._txargs(val=1))
        self.rc0.functions.submitAnswer(self.question_id, to_answer_for_contract(10001), 0).transact(self._txargs(val=2, sender=k3)) 
        self.rc0.functions.submitAnswer(self.question_id, to_answer_for_contract(10002), 0).transact(self._txargs(val=5, sender=k4)) 

        self.rc0.functions.submitAnswer(self.question_id, to_answer_for_contract(10002), 5).transact(self._txargs(val=(22+5), sender=k5)) 

    @unittest.skipIf(WORKING_ONLY, "Not under construction")
    def test_simple_bond_claim(self):

        k0 = self.web3.eth.accounts[0]

        self.rc0.functions.submitAnswer(self.question_id, to_answer_for_contract(12345), 0).transact(self._txargs(val=3)) 

        self._advance_clock(33)

        self.assertEqual(from_answer_for_contract(self.rc0.functions.getFinalAnswer(self.question_id).call()), 12345)

        self.rc0.functions.claimWinnings(self.question_id, [decode_hex("0x00")], [k0], [3], [to_answer_for_contract(12345)]).transact()
        self.assertEqual(self.rc0.functions.balanceOf(k0).call(), 3+1000)
        self.assertEqual(self.rc0.functions.balanceOf(k0).call(), 3+1000, "Winner gets their bond back plus the bounty")

    @unittest.skipIf(WORKING_ONLY, "Not under construction")
    def test_bonds(self):

        k0 = self.web3.eth.accounts[0]
        k3 = self.web3.eth.accounts[3]
        k4 = self.web3.eth.accounts[4]
        k5 = self.web3.eth.accounts[5]

        claim_args_state = []
        claim_args_addrs = []
        claim_args_bonds = []
        claim_args_answs = []

        self.assertEqual(self.rc0.functions.balanceOf(k4).call(), 0)

        with self.assertRaises(TransactionFailed):
            txid = self.rc0.functions.submitAnswer(self.question_id, to_answer_for_contract(12345), 0).transact(self._txargs(val=0)) 
            self.raiseOnZeroStatus(txid)

        claim_args_state.append(decode_hex("0x00"))
        claim_args_addrs.append(k0)
        claim_args_bonds.append(1)
        claim_args_answs.append(to_answer_for_contract(12345))
        self.rc0.functions.submitAnswer(self.question_id, to_answer_for_contract(12345), 0).transact(self._txargs(val=1)) 
        

        # "You must increase"
        with self.assertRaises(TransactionFailed):
            txid = self.rc0.functions.submitAnswer(self.question_id, to_answer_for_contract(10001), 0).transact(self._txargs(val=1, sender=k3)) 
            self.raiseOnZeroStatus(txid)

        claim_args_state.append(self.rc0.functions.questions(self.question_id).call()[QINDEX_HISTORY_HASH])
        claim_args_addrs.append(k3)
        claim_args_bonds.append(2)
        claim_args_answs.append(to_answer_for_contract(10001))
        self.rc0.functions.submitAnswer(self.question_id, to_answer_for_contract(10001), 0).transact(self._txargs(val=2, sender=k3))

        # We will ultimately finalize on this answer
        claim_args_state.append(self.rc0.functions.questions(self.question_id).call()[QINDEX_HISTORY_HASH])
        claim_args_addrs.append(k4)
        claim_args_bonds.append(4)
        claim_args_answs.append(to_answer_for_contract(10002))
        self.rc0.functions.submitAnswer(self.question_id, to_answer_for_contract(10002), 0).transact(self._txargs(val=4, sender=k4)) 

        # You have to at least double
        ###with self.assertRaises(TransactionFailed):
        ###    self.rc0.functions.submitAnswer(self.question_id, to_answer_for_contract(10003), 0).transact(self._txargs(val=7)) 
        self.assertZeroStatus(self.rc0.functions.submitAnswer(self.question_id, to_answer_for_contract(10003), 0).transact(self._txargs(val=7)))

        # You definitely can't drop back to zero
        ###with self.assertRaises(TransactionFailed):
        ###    self.rc0.functions.submitAnswer(self.question_id, to_answer_for_contract(10004), 0).transact(self._txargs(val=0)) 
        self.assertZeroStatus(self.rc0.functions.submitAnswer(self.question_id, to_answer_for_contract(10004), 0).transact(self._txargs(val=0)))

        claim_args_state.append(self.rc0.functions.questions(self.question_id).call()[QINDEX_HISTORY_HASH])
        claim_args_addrs.append(k3)
        claim_args_bonds.append(11)
        claim_args_answs.append(to_answer_for_contract(10005))
        self.rc0.functions.submitAnswer(self.question_id, to_answer_for_contract(10005), 0).transact(self._txargs(val=11, sender=k3))

        # The extra amount you have to send should be passed in a parameters
        #with self.assertRaises(TransactionFailed): 
        #    self.rc0.submitAnswer(self.question_id, to_answer_for_contract(10002), 0, value=(22+5), sender=t.k5, startgas=200000) 

        claim_args_state.append(self.rc0.functions.questions(self.question_id).call()[QINDEX_HISTORY_HASH])
        claim_args_addrs.append(k5)
        claim_args_bonds.append(22)
        claim_args_answs.append(to_answer_for_contract(10002))
        self.rc0.functions.submitAnswer(self.question_id, to_answer_for_contract(10002), 11).transact(self._txargs(val=22, sender=k5)) 

        self.assertFalse(self.rc0.functions.isFinalized(self.question_id).call())

        #You can't claim the bond until the thing is finalized
        with self.assertRaises(TransactionFailed):
            txid = self.rc0.functions.claimWinnings(self.question_id, claim_args_state[::-1], claim_args_addrs[::-1], claim_args_bonds[::-1], claim_args_answs[::-1]).transact()
            self.raiseOnZeroStatus(txid)

        self._advance_clock(33)

        self.assertEqual(from_answer_for_contract(self.rc0.functions.getFinalAnswer(self.question_id).call()), 10002)

        # First right answerer gets:
        #  - their bond back (4)
        #  - their bond again (4)
        #  - the accumulated bonds until their last answer (1 + 2)

        k4bal = 4 + 4 + 1 + 2
        self.rc0.functions.claimWinnings(self.question_id, claim_args_state[::-1], claim_args_addrs[::-1], claim_args_bonds[::-1], claim_args_answs[::-1]).transact()

        self.assertEqual(self.rc0.functions.balanceOf(k4).call(), k4bal, "First answerer gets double their bond, plus earlier bonds")

        # Final answerer gets:
        #  - their bond back (22)
        #  - the bond of the previous guy, who was wrong (11)
        #  - ...minus the payment to the lower guy (-4)
        k5bal = 22 + 11 - 4 + 1000
        self.assertEqual(self.rc0.functions.balanceOf(k5).call(), k5bal, "Final answerer gets the bounty, plus their bond, plus earlier bonds up to when they took over the answer, minus the bond of the guy lower down with the right answer")

        self.assertEqual(self.rc0.functions.balanceOf(k3).call(), 0, "Wrong answerers get nothing")

        starting_bal = self.web3.eth.getBalance(k5)
        txid = self.rc0.functions.withdraw().transact(self._txargs(sender=k5))
        rcpt = self.web3.eth.getTransactionReceipt(txid)
        gas_spent = rcpt['cumulativeGasUsed']

        ending_bal = self.web3.eth.getBalance(k5)

        self.assertEqual(ending_bal, starting_bal + k5bal - gas_spent)

        self.assertEqual(self.rc0.functions.balanceOf(k5).call(), 0)

        


    @unittest.skipIf(WORKING_ONLY, "Not under construction")
    def test_bond_bulk_withdrawal_other_user(self):

        k3 = self.web3.eth.accounts[3]

        st = None
        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1001, 0, 2, k3)
        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1001, 2, 4, k3)
        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1001, 4, 8, k3)
        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1001, 8, 16, k3)
        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1001, 16, 32, k3)
        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1001, 32, 64, k3)
        claimable = 64+32+16+8+4+2+1000

        self._advance_clock(11)

        self.assertEqual(self.rc0.functions.balanceOf(k3), 0)

        # Have an unconnected user do the claim
        # This will leave the balance in the contract rather than withdrawing it
        self.rc0.functions.claimMultipleAndWithdrawBalance([self.question_id], [len(st['hash'])], st['hash'], st['addr'], st['bond'], st['answer']).transact(self._txargs(sender=k5))
        
        self.assertEqual(self.rc0.functions.balanceOf(k3).call(), claimable)


    @unittest.skipIf(WORKING_ONLY, "Not under construction")
    def test_bond_bulk_withdrawal_other_user(self):

        k3 = self.web3.eth.accounts[3]

        st = None
        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1001, 0, 2, k3)
        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1001, 2, 4, k3)
        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1001, 4, 8, k3)
        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1001, 8, 16, k3)
        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1001, 16, 32, k3)
        st = self.submitAnswerReturnUpdatedState( st, self.question_id, 1001, 32, 64, k3)
        claimable = 64+32+16+8+4+2+1000

        self._advance_clock(33)

        starting_bal = self.web3.eth.getBalance(k3)

        # Have the user who gets all the cash do the claim
        # This will empty their balance from the contract and assign it to their normal account
        txid = self.rc0.functions.claimMultipleAndWithdrawBalance([self.question_id], [len(st['hash'])], st['hash'], st['addr'], st['bond'], st['answer']).transact(self._txargs(sender=k3))
        rcpt = self.web3.eth.getTransactionReceipt(txid)
        ending_bal = self.web3.eth.getBalance(k3)
        gas_used = rcpt['cumulativeGasUsed']

        self.assertEqual(starting_bal+claimable-gas_used, ending_bal)
        self.assertEqual(self.rc0.functions.balanceOf(k3).call(), 0, "All funds are gone from the contract once withdrawal is complete")

    @unittest.skipIf(WORKING_ONLY, "Not under construction")
    def test_withdrawal(self):

        k5 = self.web3.eth.accounts[5]

        self.rc0.functions.submitAnswer(self.question_id, to_answer_for_contract(12345), 0).transact(self._txargs(val=100, sender=k5))
        self._advance_clock(33)
        self.rc0.functions.claimWinnings(self.question_id, [decode_hex("0x00")], [k5], [100], [to_answer_for_contract(12345)]).transact(self._txargs(sender=k5))

        starting_deposited = self.rc0.functions.balanceOf(k5).call()
        self.assertEqual(starting_deposited, 1100)

        gas_used = 0
        starting_bal = self.web3.eth.getBalance(k5)

        txid = self.rc0.functions.withdraw().transact(self._txargs(sender=k5))
        rcpt = self.web3.eth.getTransactionReceipt(txid)
        gas_used = rcpt['cumulativeGasUsed']
        ending_bal = self.web3.eth.getBalance(k5)

        self.assertEqual(self.rc0.functions.balanceOf(k5).call(), 0)
        self.assertEqual(ending_bal, starting_bal + starting_deposited - gas_used)

        return

    @unittest.skipIf(WORKING_ONLY, "Not under construction")
    def test_submit_answer_for_withdrawal(self):

        if REALITIO_CONTRACT != 'Realitio_v2_1':
            print("Skipping test_submit_answer_for_withdrawal, submitAnswerFor is not a feature of this contract")
            return

        k4 = self.web3.eth.accounts[4]
        k5 = self.web3.eth.accounts[5]

        with self.assertRaises(TransactionFailed):
            txid = self.rc0.functions.submitAnswerFor(self.question_id, to_answer_for_contract(12345), 0, "0x0000000000000000000000000000000000000000").transact(self._txargs(val=100, sender=k4))
            self.raiseOnZeroStatus(txid)

        self.rc0.functions.submitAnswerFor(self.question_id, to_answer_for_contract(12345), 0, k5).transact(self._txargs(val=100, sender=k4))
        self._advance_clock(33)
        self.rc0.functions.claimWinnings(self.question_id, [decode_hex("0x00")], [k5], [100], [to_answer_for_contract(12345)]).transact(self._txargs(sender=k5))

        starting_deposited = self.rc0.functions.balanceOf(k5).call()
        self.assertEqual(starting_deposited, 1100)

        gas_used = 0
        starting_bal = self.web3.eth.getBalance(k5)

        txid = self.rc0.functions.withdraw().transact(self._txargs(sender=k5))
        rcpt = self.web3.eth.getTransactionReceipt(txid)
        gas_used = rcpt['cumulativeGasUsed']
        ending_bal = self.web3.eth.getBalance(k5)

        self.assertEqual(self.rc0.functions.balanceOf(k5).call(), 0)
        self.assertEqual(ending_bal, starting_bal + starting_deposited - gas_used)

        return


    @unittest.skipIf(WORKING_ONLY, "Not under construction")
    def test_arbitrator_fee_received(self):
        self.assertEqual(self.rc0.functions.balanceOf(self.arb0.address).call(), 100)
        
    @unittest.skipIf(WORKING_ONLY, "Not under construction")
    def test_ask_question_gas(self):

        txid = self.rc0.functions.askQuestion(
            0,
            "my question 2",
            self.arb0.address,
            10,
            0,
            0
        ).transact(self._txargs(val=1100))
        rcpt = self.web3.eth.getTransactionReceipt(txid)
        gas_used = rcpt['cumulativeGasUsed']
        #self.assertEqual(gas_used, 120000)
        self.assertTrue(gas_used < 110000)
    
    @unittest.skipIf(WORKING_ONLY, "Not under construction")
    def test_answer_question_gas(self):

        txid = self.rc0.functions.submitAnswer(self.question_id, to_answer_for_contract(12345), 0).transact(self._txargs(val=1))
        rcpt = self.web3.eth.getTransactionReceipt(txid)

        self.assertTrue(rcpt['cumulativeGasUsed'] < 100000)

        # NB The second answer should be cheaper than the first.
        # This is what we want, because you may need to be able to get a challenge through at busy times

        txid2 = self.rc0.functions.submitAnswer(self.question_id, to_answer_for_contract(12346), 0).transact(self._txargs(val=2)) 
        rcpt = self.web3.eth.getTransactionReceipt(txid2)
        self.assertTrue(rcpt['cumulativeGasUsed'] < 56000)

    @unittest.skipIf(WORKING_ONLY, "Not under construction")
    def test_question_fee_withdrawal(self):

        k3 = self.web3.eth.accounts[3]
        k4 = self.web3.eth.accounts[4]
        k5 = self.web3.eth.accounts[5]
        k7 = self.web3.eth.accounts[7]

        start_bal = self.rc0.functions.balanceOf(self.arb0.address).call()
        self.arb0.functions.setQuestionFee(321).transact()

        question_id = self.rc0.functions.askQuestion(
            0,
            "my question 3",
            self.arb0.address,
            10,
            0,
            0
        ).transact(self._txargs(val=1000, sender=k4))

        question_id = self.rc0.functions.askQuestion(
            0,
            "my question 4",
            self.arb0.address,
            10,
            0,
            0
        ).transact(self._txargs(val=2000, sender=k5))

        end_bal = self.rc0.functions.balanceOf(self.arb0.address).call()
        self.assertEqual(end_bal - start_bal, (321*2))

        start_arb_bal = self.web3.eth.getBalance(self.arb0.address)
        txid = self.arb0.functions.callWithdraw().transact(self._txargs(sender=k7))
        rcpt = self.web3.eth.getTransactionReceipt(txid)
        end_arb_bal = self.web3.eth.getBalance(self.arb0.address)

        self.assertEqual(end_arb_bal - start_arb_bal, 100 + (321*2))
        self.assertEqual(self.rc0.functions.balanceOf(self.arb0.address).call(), 0)


    @unittest.skipIf(WORKING_ONLY, "Not under construction")
    def test_question_fees(self):

        k4 = self.web3.eth.accounts[4]
        k5 = self.web3.eth.accounts[5]

        # Treat k5 as the arbitrator for these purposes, although really the arbitrator would be a contract
        self.rc0.functions.setQuestionFee(123).transact(self._txargs(sender=k5))

        # Should fail with insufficient payment to cover the question fee
        with self.assertRaises(TransactionFailed):
            txid = self.rc0.functions.askQuestion(
                0,
                "my question 2",
                k5,
                10,
                0,
                0
            ).transact( self._txargs(val=122, sender=k4))
            self.raiseOnZeroStatus(txid)

        txid = self.rc0.functions.askQuestion(
            0,
            "my question 2",
            k5,
            10,
            0,
            0
        ).transact(self._txargs(val=126, sender=k4))
        question_id = calculate_question_id(0, "my question 2", k5, 10, 0, 0, k4)

        bounty = self.rc0.functions.questions(question_id).call()[QINDEX_BOUNTY]
        self.assertEqual(bounty, 126-123, "The bounty is what's left after the question fee is deducted")

        question_id = self.rc0.functions.askQuestion(
            0,
            "my question 3",
            k5,
            10,
            0,
            0
        ).transact(self._txargs(val=122, sender=k5))
        question_id = calculate_question_id(0, "my question 3", k5, 10, 0, 0, k5)

        bounty = self.rc0.functions.questions(question_id).call()[QINDEX_BOUNTY]
        self.assertEqual(bounty, 122, "The arbitrator isn't charged their fee, so their whole payment goes to the bounty")

    @unittest.skipIf(WORKING_ONLY, "Not under construction")
    def test_arbitrator_metadata(self):

        k0 = self.web3.eth.accounts[0]
        k1 = self.web3.eth.accounts[1]

        self.assertEqual(self.arb0.functions.metadata().call(), '')

        with self.assertRaises(TransactionFailed):
            txid = self.arb0.functions.setMetaData("oink").transact(self._txargs(sender=k1))
            self.raiseOnZeroStatus(txid)

        self.arb0.functions.setMetaData("oink").transact(self._txargs(sender=k0))
        self.assertEqual(self.arb0.functions.metadata().call(), 'oink')


    @unittest.skipIf(WORKING_ONLY, "Not under construction")
    def test_arbitrator_registered_wallet(self):

        k2 = self.web3.eth.accounts[2]
        k4 = self.web3.eth.accounts[4]
        k5 = self.web3.eth.accounts[5]
        k7 = self.web3.eth.accounts[7]

        start_bal = self.rc0.functions.balanceOf(self.arb0.address).call()
        self.arb0.functions.setQuestionFee(321).transact()

        question_id = self.rc0.functions.askQuestion(
            0,
            "my question 3",
            self.arb0.address,
            10,
            0,
            0
        ).transact(self._txargs(val=1000, sender=k4))

        question_id = self.rc0.functions.askQuestion(
            0,
            "my question 4",
            self.arb0.address,
            10,
            0,
            0
        ).transact(self._txargs(val=2000, sender=k5))

        end_bal = self.rc0.functions.balanceOf(self.arb0.address).call()
        self.assertEqual(end_bal - start_bal, (321*2))

        with self.assertRaises(TransactionFailed):
            txid = self.arb0.functions.withdrawToRegisteredWallet().transact()
            self.raiseOnZeroStatus(txid)

        with self.assertRaises(TransactionFailed):
            txid = self.arb0.functions.updateRegisteredWallet(t.a8).transact(self._txargs(sender=k2))
            self.raiseOnZeroStatus(txid)
        
        self.arb0.functions.updateRegisteredWallet(t.a8).transact()
        start_arb_bal = self.web3.eth.getBalance(t.a8)

        self.arb0.functions.callWithdraw().transact(self._txargs(sender=k7))
        self.arb0.functions.withdrawToRegisteredWallet().transact(self._txargs(sender=k4))

        end_arb_bal = self.web3.eth.getBalance(t.a8)

        self.assertEqual(end_arb_bal - start_arb_bal, (100+321+321))
        self.assertEqual(self.rc0.functions.balanceOf(self.arb0.address).call(), 0)


if __name__ == '__main__':
    main()


