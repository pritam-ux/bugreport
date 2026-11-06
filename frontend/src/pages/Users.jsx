import { useState } from 'react'
import { api, useApi } from '../api/client.js'
import { Card, Notice, PageHeader, SelectControl, Spinner, formatDate } from '../components/ui.jsx'

const ROLES = ['Admin', 'Developer', 'Reporter']

export default function UsersPage() {
  const { data, error, loading, reload, setData } = useApi('/users')
  const [actionError, setActionError] = useState(null)

  const change = async (user, role) => {
    setActionError(null)
    try {
      const saved = await api.put(`/users/${user.user_id}/role`, { role })
      setData(data.map((u) => (u.user_id === saved.user_id ? saved : u)))
    } catch (err) {
      setActionError(err.message)
    }
  }

  return (
    <>
      <PageHeader title="User access" description="New accounts start as Reporters. Change a role here to grant more access." />
      {(actionError || (error && !data)) && <div className="mb-3"><Notice tone="error">{actionError || error}</Notice></div>}
      {loading && !data && <Spinner />}
      {data && (
        <Card>
          <div className="-m-5 overflow-x-auto">
            <table className="w-full min-w-[620px] text-sm">
              <thead>
                <tr className="border-b border-line text-left text-ink-muted">
                  <th className="px-5 py-3 font-medium">Name</th>
                  <th className="px-3 py-3 font-medium">Email</th>
                  <th className="px-3 py-3 font-medium">Joined</th>
                  <th className="px-5 py-3 font-medium">Role</th>
                </tr>
              </thead>
              <tbody>
                {data.map((user) => (
                  <tr key={user.user_id} className="border-b border-line/70 last:border-0">
                    <td className="px-5 py-2.5 font-medium">{user.name}</td>
                    <td className="px-3 py-2.5 text-ink-soft">{user.email}</td>
                    <td className="px-3 py-2.5 text-ink-soft">{formatDate(user.created_at)}</td>
                    <td className="w-44 px-5 py-2.5">
                      <SelectControl aria-label={`Role for ${user.name}`} options={ROLES} value={user.role} onChange={(e) => change(user, e.target.value)} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </>
  )
}
