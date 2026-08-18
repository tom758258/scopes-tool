import { cancelJob, getJob, submitJob } from "/static/api.js";

export async function runJob(command, parameters, context, onUpdate) {
  const submitted = await submitJob({ command, parameters, ...context });
  onUpdate({
    job_id: submitted.job_id,
    command,
    status: submitted.status || "queued",
  });
  let job = await getJob(submitted.job_id);
  onUpdate(job);
  while (["queued", "running"].includes(job.status)) {
    await new Promise((resolve) => setTimeout(resolve, 250));
    job = await getJob(submitted.job_id);
    onUpdate(job);
  }
  return job;
}

export async function requestCancel(jobId) {
  return cancelJob(jobId);
}
