"""Unmodified requirement identity parser from the completed three-seed report."""
import re
from collections import defaultdict

def parse_report(text):
    chunks = defaultdict(list)
    for match in re.finditer(r'>> (Passed|Failed) Requirement\n(.*?)(?=>> (?:Passed|Failed) Requirement|\Z)', text, re.S):
        description = match[2].split('```')[0]
        description = '\n'.join(l for l in description.splitlines() if not l.startswith('─') and l.strip() != 'None')
        description = ' '.join(description.split())
        chunks[description].append((match[1] == 'Passed', match[2]))
    parsed = {}
    duplicate = 'assert user_id to message mapping from notifications match private_data.venmo_user_id_to_notification_messages'
    for description, matches in chunks.items():
        assert description
        if len(matches) == 1:
            parsed[description] = matches[0][0]
            continue
        assert description == duplicate and len(matches) == 2
        identities = {'venmo_user_id_to_notification_messages', 'venmo_user_id_to_notification_payment_request_ids'}
        identified, passed_without_code = {}, []
        for passed, snippet in matches:
            if passed:
                passed_without_code.append(passed)
            else:
                code = snippet.split('```python', 1)[1]
                names = re.findall(r'(venmo_user_id_to_notification_(?:messages|payment_request_ids)) =', code)
                assert len(names) == 1 and names[0] not in identified
                identified[names[0]] = False
        remaining = identities - identified.keys()
        assert len(remaining) == len(passed_without_code)
        identified.update({name: True for name in remaining})
        for name, passed in identified.items():
            parsed[description + ' [code: ' + name + ']'] = passed
    return parsed
