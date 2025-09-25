### BEGIN: .env.example
GENESYS_CLIENT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
GENESYS_CLIENT_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
GENESYS_ENV=usw2.pure.cloud

ELASTIC_URL=https://elastic.example.com:9200
# Choose one style:
ELASTIC_AUTH=elastic:YourPasswordHere
# or Bearer token from an Elastic API key (id:secret base64):
# ELASTIC_AUTH=ApiKey <base64IdColonSecret>
# or:
# ELASTIC_AUTH=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9... (plain Bearer)
### END: .env.example
