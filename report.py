import stripe
from woocommerce import API
from datetime import date, datetime
import sys
import re
from decimal import *
import calendar
import json
from collections import OrderedDict, defaultdict
import math
import argparse

# I know, the rest of this suuuucks. but it works. So take that!

parser = argparse.ArgumentParser(description='Confluent Stripe monthly breakdowns report generator')
parser.add_argument('start', metavar='yyyy-mm-dd', help='Month to start from')
parser.add_argument('end', metavar='yyyy-mm-dd', default=None, help='Month to end with (inclusive)')
parser.add_argument('-p', '--preliminary', dest='preliminary', action='store_true', default=False, help='Mark the last month as being preliminary')

args = parser.parse_args()
preliminary = args.preliminary

start = datetime.strptime(args.start, "%Y-%m-%d")
start = date(start.year, start.month, 1)

with open('config.json') as file:    
    keys = json.load(file)

end = args.end
if end:
    end = datetime.strptime(end, "%Y-%m-%d")
else:
    end = date.today()
end = date(end.year + (1 if end.month == 12 else 0), 1 if end.month == 12 else end.month + 1, 1)

single_month = date(end.year - (1 if end.month == 1 else 0), 12 if end.month == 1 else end.month - 1, 1).strftime("%Y-%m-%d") == date(start.year, start.month, 1).strftime("%Y-%m-%d")

cache = dict()
wcapi = API(
    url=keys['woocommerce']['url'],
    consumer_key=keys['woocommerce']['consumer_key'],
    consumer_secret=keys['woocommerce']['consumer_secret'],
    wp_api=True,
    version="wc/v2",
    query_string_auth=True
)

# I wish they had an auto-paginate feature like the Stripe API does. Also they don't tell
# you that per_page has a maximum of 100 (or between 100 and 200) that if exceeded causes
# the API to default to the low value of 3! We won't really have 100 items, practically,
# as four months amounted to about 27 items, but it does help ensure everything may only
# need one request to fetch instead of the default of 10 which requires 3 requests.
page = 1
data = True
while data:
    response = wcapi.get("orders?after=" + start.strftime("%Y-%m-%dT00:00:00.000%z") + "&before=" + end.strftime("%Y-%m-%dT00:00:00.000%z") + "&orderby=id&per_page=100&page=" + str(page));
    pages = int(response.headers['X-WP-TotalPages'])
    orders = response.json()
    print("Fetched orders from store.confluent.space (Page " + str(page) + " of " + str(pages) + ")")
    for item in range(0, len(orders)):
        cache[orders[item]["id"]] = orders[item]
    print("Processed orders (Page " + str(page) + " of " + str(pages) + ")")
    page += 1
    if page > pages:
        data = False

stripe.api_key = keys['stripe']['secret_key']
list = stripe.Charge.list(limit=100, created={'gte': calendar.timegm(start.timetuple()), 'lt': calendar.timegm(end.timetuple())})
charges = []
print("Fetched charges from Stripe")

for item in list.auto_paging_iter():
    charges.append(item)
print("Processed charges from Stripe")
print("")

lastTallies = None
tdate = None

tallies = {}
tallies["memberships"] = 0
tallies["donations"] = 0
tallies["classes"] = 0
tallies["retail"] = 0
tallies["unknown"] = 0
tallies["total"] = 0
tallies["fees"] = 0

tallies["other"] = 0
tallies["bold"] = 0
tallies["basic"] = 0
tallies["business"] = 0
tallies["partnership"] = 0
tallies["twenfoursev"] = 0

arrears = dict()

def leftpad(value):
    length = len(str(math.floor(value)))
    value = str(value)
    for i in range(0, max(0, 4 - length)):
        value = " " + value
    if value.find(".") == len(value) - 2:
        value += "0"
    return value

def print_tallies(month, lastTallies, tallies, arrears, preliminary=False):
    if lastTallies is None:
        lastTallies = defaultdict(Decimal)
    else:
        print("")
    if preliminary:
        month += " (Preliminary)"
    print("*" + month + ":*")
    print("  Memberships: $" + leftpad(Decimal(tallies["memberships"] - lastTallies["memberships"]) / 100))
    print("  (Basic $25): $" + leftpad(Decimal(tallies["bold"] - lastTallies["bold"]) / 100))
    print("  (Basic $35): $" + leftpad(Decimal(tallies["basic"] - lastTallies["basic"]) / 100))
    print("(Partnership): $" + leftpad(Decimal(tallies["partnership"] - lastTallies["partnership"]) / 100))
    print("   (Business): $" + leftpad(Decimal(tallies["business"] - lastTallies["business"]) / 100))
    print("       (24/7): $" + leftpad(Decimal(tallies["twenfoursev"] - lastTallies["twenfoursev"]) / 100))
    if tallies["other"] - lastTallies["other"] > 0:
        print("    (Unknown): $" + leftpad(Decimal(tallies["other"] - lastTallies["other"]) / 100))
    print("    Donations: $" + leftpad(Decimal(tallies["donations"] - lastTallies["donations"]) / 100))
    print("      Classes: $" + leftpad(Decimal(tallies["classes"] - lastTallies["classes"]) / 100))
    print("  Misc Retail: $" + leftpad(Decimal(tallies["retail"] - lastTallies["retail"]) / 100))
    if tallies["unknown"] - lastTallies["unknown"] > 0:
        print("      Unknown: $" + leftpad(Decimal(tallies["unknown"] - lastTallies["unknown"]) / 100))
    print("        Total: $" + leftpad(Decimal(tallies["total"] - lastTallies["total"]) / 100))
    print("         Fees: $" + leftpad((tallies["fees"] - lastTallies["fees"]) / 100))

    if len(arrears) > 0:
        print("")
        print("In arrears:")
        for key in arrears:
            if len(arrears[key]) > 0:
                output = "  " + key + ": "
                for m in arrears[key]:
                    output += m + ", "
                print(output[0:-2])

def tallyfee (tallies, amount):
    fee = amount * Decimal('.029') + Decimal('30')
    fee2 = fee
    if getcontext().divmod(fee, 1)[1] * 100 >= 50:
        fee = fee.quantize(1, rounding=ROUND_UP)
    else:
        fee = fee.quantize(1, rounding=ROUND_DOWN)
    tallies["fees"] += fee

def nonMembershipCharge (charge):
    refunded = charge["amount_refunded"] > 0
    descr = charge["description"]
    match = re.search("Confluent - Order (\d+)", descr)
    if match and int(match.group(1)) in cache:
        entry = cache[int(match.group(1))]
        products = entry["line_items"]
        for product in range(0, len(products)):
            price = products[product]["price"] * products[product]["quantity"] * 100 # it's in $ not cents
            id = products[product]["product_id"]
            if id == 669: # Donation
                tallies["donations"] += price
            elif id == 1239: # Firing fee
                tallies["retail"] += price
            else:
                if refunded:
                    refund = charge["amount_refunded"]
                    price = price - refund
                    refunded = False
                tallies["classes"] += price
        tallies["total"] += price
        tallyfee(tallies, Decimal(int(float(entry["total"])) * 100))
    else:
        amount = charge["amount"]
        print(charge["description"] + ", " + str(amount));
        refund = charge["amount_refunded"]
        tallyfee(tallies, Decimal(amount))
        amount = amount - refund
        tallies["unknown"] += amount
        tallies["total"] += amount

for item in range(len(charges) - 1, -1, -1):
    charge = charges[item]
    created = datetime.utcfromtimestamp(charge["created"])
    month = created.strftime("%Y-%m")
    day = created.day
    if tdate is None:
        tdate = created
        smonth = tdate.strftime("%B")
    if created.month != tdate.month:
        print_tallies(tdate.strftime("%B"), lastTallies, tallies, arrears)
        tdate = created
        lastTallies = tallies.copy()
        lastTallies["fees"] = Decimal(lastTallies["fees"])
    descr = charge["description"]
    match = None
    if descr:
        match = re.search("Confluent - Order (\d+)", descr)
    if charge["customer"]:
        if charge["failure_code"]:
            if not charge["receipt_email"] in arrears:
                arrears[charge["receipt_email"]] = OrderedDict()
            arrears[charge["receipt_email"]][month] = day
        elif match and int(match.group(1)) in cache:
            nonMembershipCharge(charge)
        else:
            # They paid later in the month to make up for the failed charge
            if charge["receipt_email"] in arrears and month in arrears[charge["receipt_email"]] and arrears[charge["receipt_email"]][month] <= day:
                del arrears[charge["receipt_email"]][month]
                if len(arrears[charge["receipt_email"]]) == 0:
                    del arrears[charge["receipt_email"]]
            membership = charge["amount"]
            refund = charge["amount_refunded"]
            net = membership - refund
            if membership % 10000 == 0:
                tallies["twenfoursev"] += net
            elif membership % 6500 == 0:
                tallies["business"] += net
            elif membership % 5000 == 0:
                tallies["partnership"] += net
            elif membership % 3500 == 0:
                tallies["basic"] += net
            elif membership % 2500 == 0:
                tallies["bold"] += net
            # 2017-10-02 / Kimberly membership change Stripe proration fail ($5.05 proration "fee")
            elif membership == 4005:
                tallies["basic"] += 3500
                tallies["other"] += 505
            else:
                tallies["other"] += net
            tallyfee(tallies, Decimal(membership))
            tallies["memberships"] += membership
            tallies["total"] += net
    else:
        nonMembershipCharge(charge)

print_tallies(tdate.strftime("%B"), lastTallies, tallies, arrears, preliminary)
if not single_month:
    print("")
    print_tallies(smonth + " through " + tdate.strftime("%B"), None, tallies, arrears, preliminary)
