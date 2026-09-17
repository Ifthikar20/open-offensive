import api from './client'

export default {
  list: () => api.get('/scans/'),
  get: (id) => api.get(`/scans/${id}/`),
  create: (data) => api.post('/scans/', data),
  report: (id) => api.get(`/scans/${id}/report/`),
  events: (id, after = 0) => api.get(`/scans/${id}/events/`, { params: { after } }),
}
