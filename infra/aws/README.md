# AWS Interview Demo Infrastructure

Wave 16 selects **Amazon ECS Express Mode** as the preferred hosted-demo target. Nothing in this directory provisions resources by itself.

## Templates

- `foundation.yaml` — ECR, ECS cluster, generated access password, CloudWatch log group, ECS execution/infrastructure roles, optional AWS Budget.
- `service.yaml` — one public HTTPS ECS Express Mode service, one task minimum/maximum, fail-closed demo environment, generated access password injected from Secrets Manager.
- `github-deploy-role.yaml` — optional GitHub OIDC deployment role for an **existing** GitHub OIDC provider, restricted to one repository + `aws-demo` environment.

## Intended deployment sequence

1. An authorized operator deploys `foundation.yaml` once.
2. Build and push the application image to the ECR output URI.
3. Deploy `service.yaml` using foundation outputs.
4. Retrieve the generated demo password from Secrets Manager and share it out-of-band with the employer.
5. If GitHub deployment is desired, create the GitHub OIDC provider following current AWS guidance, deploy `github-deploy-role.yaml`, then configure repository variables and GitHub Environment protection.

See `docs/runbooks/AWS_DEPLOYMENT.md` and `docs/runbooks/AWS_TEARDOWN.md`.

**Do not deploy from this package without explicit cost authorization.**
