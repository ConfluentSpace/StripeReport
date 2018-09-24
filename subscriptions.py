import stripe
import json
import re

with open('config.json') as file:    
    keys = json.load(file)

stripe.api_key = keys['stripe']['secret_key']
active = dict()
delinquent = []
inactive = []

namecheck = re.compile('name: (.*) username: .*', re.I)

def namefix(name):
    match = namecheck.match(name)
    if match:
        name = match.group(1)
    return name

customers = stripe.Customer.list(limit=100)
for customer in customers.auto_paging_iter():
    customer['description'] = namefix(customer['description'])
    if customer['delinquent']:
        delinquent.append(customer)
    else:
        if len(customer['subscriptions']['data']):
            plan = customer['subscriptions']['data'][0]['items']['data'][0]['plan']
            if not plan['name'] in active:
                active[plan['name']] = []
            active[plan['name']].append(customer)
        else:
            inactive.append(customer)
print('Fetched subscriptions from Stripe')

plans = list(active.keys())
plans.sort()

print('')
print('Active Subscriptions:')
for name in plans:
    plan = active[name]
    plan.sort(key=lambda customer: customer['description'])
    print('  ' + name + ':')
    for customer in plan:
        print('    ' + customer['description'] + ' (' + customer['email'] + ')')
    print('')

delinquent.sort(key=lambda customer: customer['description'])

print('')
print('Delinquent Members:')
for customer in delinquent:
    plan = ''
    if len(customer['subscriptions']['data']):
        plan = ' @ ' + customer['subscriptions']['data'][0]['items']['data'][0]['plan']['name']
    print('  ' + customer['description'] + ' (' + customer['email'] + ')' + plan)

inactive.sort(key=lambda customer: customer['description'])

print('')
print('Inactive Members:')
for customer in inactive:
    print('  ' + customer['description'] + ' (' + customer['email'] + ')')
