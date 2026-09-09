import React, { useState, useEffect, useContext, createContext } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Search, BookOpen, Users, Cpu, FileText, ChevronRight, Lock, Unlock, Mail, Settings,
  LogOut, Bell, MessageSquare, Activity, BarChart2, PlusCircle, CheckCircle, AlertTriangle,
  Download, Bookmark, Share2, Filter, MoreVertical, X, Menu, Home, Grid, Lightbulb,
  FileSearch, UserPlus, Shield, Check, FileUp, Database, GitBranch, ArrowRight, ArrowLeft,
  MessageCircle, Link as LinkIcon, ThumbsUp, Send, PieChart, TrendingUp, Search as SearchIcon,
  ShieldAlert, Settings2, Sliders, ChevronDown, Book, User, Calendar
} from 'lucide-react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  BarChart, Bar, PieChart as RePieChart, Pie, Cell, AreaChart, Area
} from 'recharts';
import {
  theme, MOCK_THESES, MOCK_USERS, MOCK_MESSAGES, useAppRouter,
  Button, Input, Card, Badge, PublicLayout, AuthenticatedLayout, AuthContainer,
  ThesisCard, UploadWizardNav, pageVariants, listVariants, itemVariants
} from '../components/shared';

const Screen19MyProjects = () => {
  const { navigate } = useAppRouter();
  return (
    <AuthenticatedLayout title="My Research Projects">
      <div className="flex justify-end mb-6">
        <Button onClick={() => navigate('upload')}><PlusCircle className="w-4 h-4 mr-2"/> Upload New</Button>
      </div>
      <Card className="overflow-hidden">
        <table className="min-w-full divide-y divide-slate-200">
          <thead className="bg-slate-50">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider">Project Title</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider">Status</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider">Access</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider">Date</th>
              <th className="px-6 py-3 text-right text-xs font-medium text-slate-500 uppercase tracking-wider">Actions</th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-slate-200">
            {MOCK_THESES.slice(0, 2).map((thesis) => (
              <tr key={thesis.id} className="hover:bg-slate-50">
                <td className="px-6 py-4">
                  <div className="text-sm font-medium text-slate-900 line-clamp-1">{thesis.title}</div>
                  <div className="text-xs text-slate-500">Undergraduate Thesis</div>
                </td>
                <td className="px-6 py-4 whitespace-nowrap">
                  <Badge variant={thesis.status === 'Published' ? 'green' : 'gray'}>{thesis.status}</Badge>
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-slate-500 flex items-center">
                  <Unlock className="w-3 h-3 mr-1"/> Public
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-slate-500">
                  Oct 24, 2023
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                  <button onClick={() => navigate('edit-thesis')} className="text-[#00502F] hover:text-[#003d24] mr-4">Edit</button>
                  <button onClick={() => navigate('personal-analytics')} className="text-slate-500 hover:text-slate-700">Analytics</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </AuthenticatedLayout>
  );
};

export default Screen19MyProjects;
