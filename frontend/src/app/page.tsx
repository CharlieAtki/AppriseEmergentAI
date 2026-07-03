import { auth } from '@clerk/nextjs/server'
import { redirect } from 'next/navigation'

export default async function HomePage() {
  const { orgId } = await auth()

  if (orgId) redirect(`/orgs/${orgId}/workspaces`)
  redirect('/sign-in')
}
