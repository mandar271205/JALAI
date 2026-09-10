# JalRakshak AI Mobile

Expo/React Native client for citizen safety and field-responder operations. The app communicates only with the public `/api/v1` backend, keeps credentials in SecureStore, and labels unavailable backend capabilities honestly.

## Run

```bash
npm install
cp .env.example .env
npm run start
```

`EXPO_PUBLIC_AUTH_MODE=mock` is for local backend development only. Production requires a bearer token issued by the configured identity flow; this repository's backend currently validates tokens but does not expose a login/token-issuance endpoint.

OS push requires a development/native build and valid Firebase/APNs/Expo project configuration. Expo Go is not presented as a live-push environment.

See `../docs/MOBILE_FRONTEND_IMPLEMENTATION_MATRIX.md` and `../docs/MOBILE_E2E_SMOKE.md`.
