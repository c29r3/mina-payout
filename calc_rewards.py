from tabulate import tabulate
import GraphQL
import os
import decimal
from pprint import pprint

################################################################
# Define the payout calculation here
################################################################
public_key = "B62qjhiEXP45KEk8Fch4FnYJQ7UMMfiR3hq9ZeMUZ8ia3MbfEteSYDg"  # Public key of the block producer
decimal_       = 1e9
staking_epoch  = 8  # To ensure we only get blocks from the current staking epoch as the ledger may be different
fee            = 0.07  # The fee percentage to charge
foundation_fee = 0.05
foundation_secure_sum = 0.05 * decimal_
min_height     = 0  # This can be the last known payout or this could vary the query to be a starting date
latest_block   = 0
confirmations  = 15  # Can set this to any value for min confirmations up to `k`
COINBASE       = 720


def float_to_string(number, precision=9):
    return '{0:.{prec}f}'.format(
        decimal.Context(prec=100).create_decimal(str(number)),
        prec=precision,
    ).rstrip('0').rstrip('.') or '0'


def write_to_file(data_string: str, file_name: str, mode: str = "w"):
    with open(file_name, mode) as some_file:
        some_file.write(data_string + "\n")


with open("foundation_addresses.txt", "r") as f:
    foundation_delegations = f.read().split("\n")

try:
    ledger_hash = GraphQL.getLedgerHash(epoch=staking_epoch)
    print(ledger_hash)
    ledger_hash = ledger_hash["data"]["blocks"][0] \
                             ["protocolState"]["consensusState"] \
                             ["stakingEpochData"]["ledger"]["hash"]
except Exception as e:
    print(e)
    exit("Issue getting ledger_hash from GraphQL")

if latest_block == 0:
    # Get the latest block height
    latest_block = GraphQL.getLatestHeight()
else:
    latest_block = {'data': {'blocks': [{'blockHeight': latest_block}]}}

if not latest_block:
    exit("Issue getting the latest height")
assert latest_block["data"]["blocks"][0]["blockHeight"] > 1

# Only ever pay out confirmed blocks
max_height = latest_block["data"]["blocks"][0]["blockHeight"] - confirmations
assert max_height <= latest_block["data"]["blocks"][0]["blockHeight"]

print(f"This script will payout from blocks {min_height} to {max_height}")

# Initialize some stuff
total_staking_balance = 0
total_staking_balance_unlocked = 0
total_staking_balance_foundation = 0
payouts = []
all_block_rewards = 0
all_x2_block_rewards = 0
total_snark_fee = 0
all_blocks_total_fees = 0
blocks_included = []
store_payout = []

# Get the staking ledger for an epoch
try:
    staking_ledger = GraphQL.getStakingLedger({
        "delegate": public_key,
        "ledgerHash": ledger_hash,
    })
except Exception as e:
    print(e)
    exit("Issue getting staking ledger from GraphQL")

if not staking_ledger["data"]["stakes"]:
    exit("We have no stakers")

csv_header_delegates = "address;stake;foundation_delegation?"
delegator_file_name  = "delegates.csv"
write_to_file(data_string=csv_header_delegates, file_name=delegator_file_name, mode="w")

for s in staking_ledger["data"]["stakes"]:
    # skip delegates with staking balance == 0
    if s["balance"] == 0:
        continue

    if not s["timing"]:
        # 100% unlocked
        timed_weighting = "unlocked"
        total_staking_balance_unlocked += s["balance"]
    else:
        # locked tokens
        timed_weighting = "locked"

    # Is this a Foundation address
    if s["public_key"] in foundation_delegations:
        foundation_delegation = True
        total_staking_balance_foundation += s["balance"]
    else:
        foundation_delegation = False

    payouts.append({
        "publicKey":             s["public_key"],
        "total_reward":          0,
        "staking_balance":       s["balance"],
        "percentage_of_total":   0,                     # delegator's share in %, relative to total_staking_balance
        "percentage_of_SP":      0,                     # percentage of unlocked tokens from the total amount of unlocked tokens
        "timed_weighting":       timed_weighting,
        "foundation_delegation": foundation_delegation
    })

    total_staking_balance += s["balance"]
    delegator_csv_string = f'{s["public_key"]};{float_to_string(s["balance"])};{foundation_delegation}'
    write_to_file(data_string=delegator_csv_string, file_name=delegator_file_name, mode="a")

try:
    blocks = GraphQL.getBlocks({
        "creator":        public_key,
        "epoch":          staking_epoch,
        "blockHeightMin": min_height,
        "blockHeightMax": max_height,
    })
except Exception as e:
    print(e)
    exit("Issue getting blocks from GraphQL")

if not blocks["data"]["blocks"]:
    exit("Nothing to payout as we didn't win anything")

# pprint(blocks["data"]["blocks"])

csv_header_blocks = "block_height;slot;block_reward;snark_fee;tx_fee;epoch;state_hash"
blocks_file_name = f"blocks.csv"
write_to_file(data_string=csv_header_blocks, file_name=blocks_file_name, mode="w")

for b in reversed(blocks["data"]["blocks"]):
    if not b["transactions"]["coinbaseReceiverAccount"]:
        print(f"{b['blockHeight']} didn't have a coinbase so won it but no rewards.")
        continue

    if not b["canonical"]:
        print("Block not in canonical chain")
        continue

    block_height = b["blockHeight"]
    slot         = b["protocolState"]["consensusState"]["slotSinceGenesis"]
    block_reward_mina = int(b["transactions"]["coinbase"]) / decimal_
    block_reward_nano = int(b["transactions"]["coinbase"])
    snark_fee    = b["snarkFees"]
    epoch        = b["protocolState"]["consensusState"]["epoch"]
    state_hash   = b["stateHash"]
    tx_fees      = b["txFees"]

    total_snark_fee += int(snark_fee)
    all_blocks_total_fees += int(tx_fees)
    blocks_included.append(b['blockHeight'])
    if block_reward_mina > COINBASE:
        all_x2_block_rewards += block_reward_nano - (COINBASE * decimal_)
        all_block_rewards += block_reward_nano - (COINBASE * decimal_)
    else:
        all_block_rewards += block_reward_nano

    csv_string = f"{block_height};" \
                 f"{slot};" \
                 f"{block_reward_mina};" \
                 f"{float_to_string(int(snark_fee) / decimal_)};" \
                 f"{float_to_string(int(tx_fees) / decimal_)};" \
                 f"{epoch};" \
                 f"{state_hash}"
    write_to_file(data_string=csv_string, file_name=blocks_file_name, mode="a")

total_reward = all_block_rewards + all_blocks_total_fees - total_snark_fee

delegators_reward_sum = 0
payout_table = []

# remove the file to prevent invalid data in the payout file
try:
    os.remove(f'e{staking_epoch}_payouts.csv')
except:
    pass

for p in payouts:
    if p["foundation_delegation"] is True:
        p["percentage_of_total"] = float(p["staking_balance"]) / total_staking_balance
        p["total_reward"] = float(total_reward * p["percentage_of_total"] * (1 - foundation_fee) + foundation_secure_sum)

    elif p["timed_weighting"] == "unlocked":
        p["percentage_of_SP"] = float(p["staking_balance"]) / total_staking_balance_unlocked
        p["percentage_of_total"] = float(p["staking_balance"]) / total_staking_balance
        p["total_reward"]        = float(total_reward * p["percentage_of_total"] * (1 - fee))
        p["total_reward"] = p["total_reward"] + (float(all_x2_block_rewards * p["percentage_of_SP"] * (1 - fee)))

    else:
        p["percentage_of_total"] = float(p["staking_balance"]) / total_staking_balance
        p["total_reward"]        = float(total_reward * p["percentage_of_total"] * (1 - fee))

    delegators_reward_sum += p["total_reward"]

    payout_table.append([
        p["publicKey"],
        p["staking_balance"],
        float_to_string(p["total_reward"] / decimal_),
        p["foundation_delegation"],
        p["timed_weighting"]
    ])

    payout_string = f'{p["publicKey"]};' \
                    f'{float_to_string(int(p["total_reward"]))};' \
                    f'{float_to_string(p["total_reward"] / decimal_)};' \
                    f'{p["foundation_delegation"]};' \
                    f'{p["timed_weighting"]}'

    # do not pay anything if reward < 0.1 MINA
    if p["total_reward"] / decimal_ < 0.1:
        continue

    write_to_file(data_string=payout_string,
                  file_name=f'e{staking_epoch}_payouts.csv', mode='a')

# pprint(payouts)
# We now know the total pool staking balance with total_staking_balance
print(f"The pool total staking balance is:    {total_staking_balance}\n"
      f"The Foundation delegation balance is: {total_staking_balance_foundation}\n"
      f"Blocks won:                           {len(blocks_included)}\n"
      f"Delegates in the pool:                {len(payouts)}")

validator_reward = total_reward + all_x2_block_rewards - delegators_reward_sum
print(f'Supercharged rewards total: {all_x2_block_rewards}')
print(f'Total:                      {(total_reward + all_x2_block_rewards) / decimal_}')
print(f'Validator fee:              {validator_reward / decimal_}')

print(tabulate(payout_table,
               headers=["PublicKey", "Staking Balance", "Payout mina", "Foundation", "Tokens_lock_status"], tablefmt="pretty"))
