"""Passive local request/response capture; no extra API calls or policy feedback."""
def attach_capture(requester, encode):
 original=requester._request
 records=[]
 def captured(_app_name,_api_name,*args,**kwargs):
  item={'app_name':_app_name,'api_name':_api_name,
        'arguments':encode({k:v for k,v in kwargs.items() if k not in ('client','raise_on_failure','track')})}
  records.append(item)
  try:
   response=original(_app_name,_api_name,*args,**kwargs)
  except Exception as exc:
   item.update(status='raised',error_type=type(exc).__name__,error=str(exc))
   raise
  item.update(status='returned',status_code=response.status_code)
  try:item['response_json']=response.json()
  except ValueError:item['response_text']=response.text
  return response
 requester._request=captured
 return records
