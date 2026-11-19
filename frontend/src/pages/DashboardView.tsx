import { useParams } from 'react-router-dom'
import { BoardPage } from './board/BoardPage'

/** ``/dashboards/view/<id>``: a dashboard inside the app, with the sidebar. */
export default function DashboardView() {
  const { id = '' } = useParams()
  return <BoardPage key={id} id={id} />
}
