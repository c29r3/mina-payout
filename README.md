# mina-payout  
## What the script can do  
1. Support for three types of commissions. Validator commission, Fund commission, commission for supercharged blocks  
2. All data for each epoch is saved in csv files  
3. Payment of awards to all delegates in accordance with the csv file  
4. After sending payments, the script waits 20 minutes until all transactions are confirmed. If some of them disappear from mempool, then unsuccessful transactions are written to a separate file and can be sent again

## Install  
```bash
git clone https://github.com/c29r3/mina-payout.git \
&& cd mina-payout \
&& pip3 install -r requirements.txt
```

## Settings  
Take a close look at the contents of `config.yml`

## Disclaimer  
The script is provided as is. The author does not bear any responsibility for your mistakes and carelessness.

*This script based on https://github.com/garethtdavies/mina-payout-script. Thanks to Gareth Davies*
