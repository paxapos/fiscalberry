#bash

#epson tm 700ta 2gen ejemplo (no funciona pero asi me dieron los de epson)
curl --noproxy 192.168.1.38 http://192.168.1.38/fiscal.json -H "Content-Type: application/json" --data-binary datajson.json > resp.json