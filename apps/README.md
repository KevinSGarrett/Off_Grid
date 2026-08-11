# Application Area

Wave 3 will create the real `apps/api` and `apps/web` starter applications after the architecture/ADR work establishes component boundaries. The controlling baseline is FastAPI for backend and React/TypeScript/Vite/Tailwind for frontend.

Wave 1 intentionally does not add empty application stubs or fake endpoints. When this area expands, business logic must remain separated from HTTP/UI layers and the application must preserve deterministic core behavior when OpenAI and external integrations are unavailable.
