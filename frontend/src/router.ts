import { createRouter, createWebHistory } from 'vue-router';
import { isAuthenticated } from './api/authApi';
import LoginView from './views/LoginView.vue';
import RegisterView from './views/RegisterView.vue';
import DashboardView from './views/DashboardView.vue';
import WorkspaceView from './views/WorkspaceView.vue';
import BusinessAgentView from './views/BusinessAgentView.vue';
import ClosureCenterView from './views/ClosureCenterView.vue';
import HistoryView from './views/HistoryView.vue';
import ProfileView from './views/ProfileView.vue';

const businessPages = {
  production: {
    title: '生产调度看板',
    subtitle: '工单排程、产能瓶颈、交期风险与调度优化',
    agentName: 'production_scheduling',
    agentLabel: '生产调度优化',
    sample: '本周3个工单面临交期风险，CNC设备产能利用率92%，请分析瓶颈并提出排产优化建议',
  },
  quality: {
    title: '质量检测中心',
    subtitle: '缺陷分类、质量标准匹配、根因定位与改善建议',
    agentName: 'quality_inspection',
    agentLabel: '质量检测与缺陷分析',
    sample: '最近批次缺陷率上升至8%，主要缺陷为尺寸偏差和表面粗糙度，请分析根因并给出改进建议',
  },
  maintenance: {
    title: '设备监控面板',
    subtitle: '传感器状态、故障预测、维护工单与停机风险',
    agentName: 'predictive_maintenance',
    agentLabel: '设备预测性维护',
    sample: 'CNC-001主轴振动传感器读数达到12mm/s，温度65摄氏度，请预测故障风险并生成维护建议',
  },
  supplyChain: {
    title: '供应链管理',
    subtitle: '物料需求、库存预警、采购建议与供应商协同',
    agentName: 'supply_chain_management',
    agentLabel: '供应链协同管理',
    sample: '生产计划需钢材2000kg，当前库存300kg，安全库存1000kg，请分析缺料风险并生成采购建议',
  },
  process: {
    title: '工艺优化分析',
    subtitle: '工艺参数、质量反馈、良品率提升与效率优化',
    agentName: 'process_parameter_optimization',
    agentLabel: '工艺参数优化',
    sample: '热处理温度860摄氏度时良品率92%，历史数据显示840摄氏度良品率95%，请推荐最优参数组合',
  },
};

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', component: LoginView },
    { path: '/register', component: RegisterView },
    { path: '/', redirect: '/dashboard' },
    { path: '/dashboard', component: DashboardView, meta: { requiresAuth: true } },
    { path: '/workspace', component: WorkspaceView, meta: { requiresAuth: true } },
    {
      path: '/production',
      component: BusinessAgentView,
      meta: { requiresAuth: true, page: businessPages.production },
    },
    {
      path: '/quality',
      component: BusinessAgentView,
      meta: { requiresAuth: true, page: businessPages.quality },
    },
    {
      path: '/maintenance',
      component: BusinessAgentView,
      meta: { requiresAuth: true, page: businessPages.maintenance },
    },
    {
      path: '/supply-chain',
      component: BusinessAgentView,
      meta: { requiresAuth: true, page: businessPages.supplyChain },
    },
    {
      path: '/process',
      component: BusinessAgentView,
      meta: { requiresAuth: true, page: businessPages.process },
    },
    { path: '/closure', component: ClosureCenterView, meta: { requiresAuth: true } },
    { path: '/history', component: HistoryView, meta: { requiresAuth: true } },
    { path: '/profile', component: ProfileView, meta: { requiresAuth: true } },
    { path: '/:pathMatch(.*)*', redirect: '/dashboard' },
  ],
});

router.beforeEach((to) => {
  if (to.meta.requiresAuth && !isAuthenticated()) {
    return '/login';
  }
  if ((to.path === '/login' || to.path === '/register') && isAuthenticated()) {
    return '/dashboard';
  }
  return true;
});

export default router;
