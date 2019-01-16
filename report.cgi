#!/home/confluent/reports/env/bin/python3
import cgi
import os
import re
import sys

queryString = os.environ.get('QUERY_STRING', '')
match = re.match('\??start=([^&]+)&end=([^&]+)', queryString)
if match:
	match = match.groups()

print('Content-Type: text/html')
print('')
print('<!doctype html>')
print('<html>')
print('  <head>')
print('    <meta charset="utf-8">')
print('    <title>Tax Report</title>')
print('  </head>')
print('  <body>')
print('    <pre>')

if match and len(match) >= 2:
	sys.argv.append(match[0])
	sys.argv.append(match[1])
	import report
else:
	print('Not enough arguments. Query string should be similar to ?start=2018-01-01&end=2018-02-01')

print('    </pre>')
print('  <body>')
print('</html>')
