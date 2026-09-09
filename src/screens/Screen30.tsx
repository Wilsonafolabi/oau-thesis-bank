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

const Screen30ResearcherProfile = () => {
  const { navigate } = useAppRouter();
  return (
    <AuthenticatedLayout title="Researcher Profile">
      <div className="max-w-5xl mx-auto">
        {/* Profile Header */}
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden mb-8">
          <div className="h-32 bg-gradient-to-r from-[#00502F] to-[#003d24]"></div>
          <div className="px-8 pb-8 relative">
            <div className="w-24 h-24 rounded-full bg-white border-4 border-white shadow-md flex items-center justify-center text-3xl font-bold text-[#00502F] absolute -top-12">
              AO
            </div>
            <div className="mt-16 flex flex-col md:flex-row justify-between items-start md:items-center">
              <div>
                <h1 className="text-2xl font-bold text-slate-900 flex items-center">Adekunle Ojo <Badge variant="green" className="ml-3">Alumni</Badge></h1>
                <p className="text-slate-600 mt-1">B.Sc. Agricultural Engineering (2023)</p>
                <div className="flex items-center space-x-4 mt-3 text-sm text-slate-500">
                  <span className="flex items-center"><LinkIcon className="w-4 h-4 mr-1"/> GitHub</span>
                  <span className="flex items-center"><LinkIcon className="w-4 h-4 mr-1"/> ORCID</span>
                </div>
              </div>
              <div className="mt-4 md:mt-0 flex space-x-3">
                <Button onClick={() => navigate('messages')}><MessageSquare className="w-4 h-4 mr-2"/> Message</Button>
                <Button variant="secondary" onClick={() => navigate('mentorship-request')}>Request Mentorship</Button>
              </div>
            </div>
          </div>
        </div>

        <div className="flex flex-col lg:flex-row gap-8">
          <div className="flex-1 space-y-8">
            <Card className="p-6">
              <h3 className="text-lg font-bold text-slate-900 mb-3">About</h3>
              <p className="text-slate-600 text-sm leading-relaxed">
                Passionate about leveraging machine learning to solve agricultural challenges in Sub-Saharan Africa. Currently working as a Data Analyst, open to academic collaborations and mentoring current undergraduates in the Agric Engineering department.
              </p>
            </Card>
            
            <div>
              <div className="flex justify-between items-end mb-4">
                <h3 className="text-lg font-bold text-slate-900">Published Research</h3>
                <button className="text-sm text-[#00502F] hover:underline" onClick={() => navigate('researcher-activity')}>View Timeline</button>
              </div>
              <div className="space-y-4">
                <ThesisCard thesis={MOCK_THESES[0]} onClick={() => navigate('thesis-detail')} />
              </div>
            </div>
          </div>
          
          <div className="w-full lg:w-80 space-y-6">
            <Card className="p-6">
              <h3 className="font-bold text-slate-900 mb-4">Research Interests</h3>
              <div className="flex flex-wrap gap-2">
                {['Machine Learning', 'Precision Agriculture', 'Data Science', 'Python', 'GIS'].map(tag => (
                  <Badge key={tag} variant="gray">{tag}</Badge>
                ))}
              </div>
            </Card>
            <Card className="p-6">
              <h3 className="font-bold text-slate-900 mb-4 text-center">Impact Stats</h3>
              <div className="grid grid-cols-2 gap-4 text-center">
                <div>
                  <span className="block text-2xl font-bold text-[#00502F]">1.2k</span>
                  <span className="text-xs text-slate-500 uppercase">Views</span>
                </div>
                <div>
                  <span className="block text-2xl font-bold text-[#00502F]">45</span>
                  <span className="text-xs text-slate-500 uppercase">Citations</span>
                </div>
              </div>
            </Card>
          </div>
        </div>
      </div>
    </AuthenticatedLayout>
  );
};

export default Screen30ResearcherProfile;
