import pprint
from src.codaclient import CodaClient
import time
import yaml

c = yaml.load(open('config.yml', encoding='utf8'), Loader=yaml.SafeLoader)
GRAPHQL_HOST      = str(c("GRAPHQL_HOST"))
GRAPHQL_PORT      = str(c("GRAPHQL_PORT"))
VALIDATOR_NAME    = str(c("VALIDATOR_NAME"))
EPOCH             = int(c["STAKING_EPOCH_NUMBER"])
WALLET_PASSWORD   = str(c("WALLET_PASSWORD"))
default_fee       = int(c["DEFAULT_TX_FEE"])
send_from         = str(c("SEND_FROM_ADDRESS"))  # coinbase receiver
TX_CHECK_TIMER    = int(c["TX_CHECK_TIMER_SECONDS"])

MEMO              = f'e{EPOCH}_{VALIDATOR_NAME}'
FILE_WITH_PAYOUTS = f'e{EPOCH}_payouts.csv'
DECIMAL           = 1e9
TIMEOUT           = 1
TX_LIST_TO_CHECK  = []
FAILED_PAYOUTS    = 0
FAILED_PAYOUTS_FILE = f"failed_payouts_{EPOCH}.csv"
FAILED_PAYOUTS_LST  = []

with open("version", "r") as v_file:
    version = v_file.read()
print(f'Script version: {version}')

graphql = CodaClient.Client(graphql_host=GRAPHQL_HOST, graphql_port=GRAPHQL_PORT)

print(f"Epoch: {EPOCH}")
print(graphql.get_wallets())
try:
    graphql.unlock_wallet(send_from, WALLET_PASSWORD)
except:
    print("Can't unlock wallet. Check password and address")


def send_transaction(to_address, amount_nanomina, from_address=send_from,  fee_nanomina=default_fee, memo=MEMO):
    if fee_nanomina > 1e9:
        exit(f"Tx fee is too high {fee_nanomina}")

    trans_res = graphql.send_payment(to_pk=to_address,
                                     from_pk=from_address,
                                     amount=amount_nanomina,
                                     fee=fee_nanomina,
                                     memo=memo)
    # pprint.pprint(trans_res)
    return trans_res


with open(FILE_WITH_PAYOUTS, "r") as payout_file:
    payout_lst = payout_file.read().split("\n")
    payout_lst = list(filter(None, payout_lst))

for i, p in enumerate(payout_lst, start=1):
    p = p.split(";")
    delegator_addr = p[0]
    payout_in_nanomina = int(p[1])
    payout_in_mina = float(p[2])
    is_it_foundation = p[3]

    print(f'{i}\\{len(payout_lst)} '
          f'{payout_in_mina} MINA --> https://minaexplorer.com/wallet/{delegator_addr}')

    # PAYOUTS STARTS HERE
    hash_result = send_transaction(
        to_address=delegator_addr,
        amount_nanomina=payout_in_nanomina)

    with open(f"sended_txs_e{EPOCH}.csv", "a") as tx_result:
        tx_result.write(f"{hash_result}\n")
    TX_LIST_TO_CHECK.append(hash_result)
    time.sleep(TIMEOUT)


print(f'Trying to lock wallet: {send_from}')
try:
    graphql.lock_wallet(send_from)
except:
    print("Can't lock wallet")

pool = graphql.get_pooled_payments(send_from)
print(len(pool["pooledUserCommands"]))
print(pool["pooledUserCommands"])

# Let's check all transactions status
print(f'Starting verification of sent transactions. Checker timer = {TX_CHECK_TIMER / 60} min')
while len(TX_LIST_TO_CHECK):
    tx_data = ""
    print(f'{len(TX_LIST_TO_CHECK)} pending txs in the pool. Timer timeout = {TX_CHECK_TIMER} sec')
    for n, tx in enumerate(TX_LIST_TO_CHECK, start=1):
        t1 = time.time()
        tx_hash = tx["sendPayment"]["payment"]["id"]
        try:
            tx_data = graphql.get_transaction_status(tx_hash)
        except Exception as tx_status_err:
            print(f'Can\'t get TX status: {tx_status_err}')
            TX_CHECK_TIMER -= time.time() - t1
            continue

        if "error" in str(tx_data):
            print(f'Can\'t get TX status {tx_data}')
            TX_CHECK_TIMER -= time.time() - t1
            continue

        elif "pending" in str(tx_data) or "PENDING" in str(tx_data):
            print(f'Tx has pending status: https://minaexplorer.com/payment/{tx_hash}')

        elif "INCLUDED" in str(tx_data) or "included" in str(tx_data):
            print(f'Transaction sent successfully: https://minaexplorer.com/payment/{tx_hash}')
            TX_LIST_TO_CHECK.remove(tx)

        else:
            print(f'Else triggered: {tx_data}')

        time.sleep(1)

        TX_CHECK_TIMER -= time.time() - t1
        if TX_CHECK_TIMER <= 0:
            print(f'Timeout: Transaction verification took too long. Save failed transactions and exit\n'
                  f'Unconfirmed transactions: {len(TX_LIST_TO_CHECK)}')
            for tx_ in TX_LIST_TO_CHECK:
                tx_ = tx_["sendPayment"]["payment"]
                to_addr = tx_["to"]
                amount_wei = tx_["amount"]
                amount_in_mina = int(amount_wei) / 1e9
                FAILED_PAYOUTS_LST.append(f'{to_addr};{str(amount_wei)};{str(amount_in_mina)};;')
            with open(FAILED_PAYOUTS_FILE, "w") as failed_f:
                for t in FAILED_PAYOUTS_LST:
                    failed_f.write(f'{t}\n')
            print(f'Check file with failed txs - {FAILED_PAYOUTS_FILE}')
            exit(1)

        if len(TX_LIST_TO_CHECK) == 0:
            print("All transactions are successfully confirmed!")
            exit(0)
