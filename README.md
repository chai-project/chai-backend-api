# API Server
The API server provides the interface between the user interface and the backend. The definition of the API server is provided using the OpenAPI standard. This definition file is the golden standard. The UI should be designed against the OpenAPI definition, and the API is misbehaving when it does not respond to a request as defined in the OpenAPI definition. ***The UI does not necessarily need to use all the specified endpoints, and the backend can provide additional features that may not be documented in the OpenAPI specification.***


## Endpoints
Development of the endpoints specified in the Open API specification is ongoing. An overview of the implementation status is given below. The status of each endpoint is given as one of four categories:

**Missing**
: This endpoint should be supported, but no implementation exists yet.

**Basic**
: The server is aware of the endpoint and does not report a 404 error.

**Partial**
: The endpoint is partially implemented. It may not respond to all query variants, or the response may not be correct and/or complete.

**Full**
: The endpoint is fully implemented and provides a valid response for all query variations. The response may be static or randomly generated.

### Current Status

| Endpoint                    | Pos Status | 
|:----------------------------|:----------:|
| **heating endpoints**       |
| `GET` `/heating/mode`       |  **Full**  |
| `PUT` `/heating/mode`       |  **Full**  |
| `GET` `/heating/valve`      |  **Full**  |
| `GET` `/heating/profile`    |  **Full**  |
| `GET` `/heating/historic`   |  **Full**  |
| **schedule endpoints**      |
| `GET` `/schedule`           |  **Full**  |
| `PUT` `/schedule`           |  **Full**  |
| **electricity endpoints**   |
| `GET` `/electricity/prices` |  **Full**  |
| **logs endpoints**          |
| `GET` `/logs`               |  **Full**  |
| `PUT` `/logs`               |  **Full**  |
| **XAI endpoints**           |
| `GET` `/xai/region`         |  **Full**  |
| `PUT` `/xai/band`           |  **Full**  |
| `PUT` `/xai/scatter`        |  **Full**  |
