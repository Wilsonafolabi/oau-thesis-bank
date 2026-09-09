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

const Screen20EditThesis = () => {
  const { navigate } = useAppRouter();
  return (
    <AuthenticatedLayout title="Edit Thesis Metadata">
      <div className="max-w-3xl mx-auto space-y-6">
        <div className="flex justify-between items-center mb-6">
          <button className="text-sm text-slate-500 hover:text-slate-800 flex items-center" onClick={() => navigate('my-projects')}><ArrowLeft className="w-4 h-4 mr-1"/> Back</button>
          <div className="space-x-3">
            <Button variant="ghost">Cancel</Button>
            <Button onClick={() => navigate('my-projects')}>Save Changes</Button>
          </div>
        </div>
        
        <Card className="p-6">
          <h3 className="text-lg font-medium text-slate-900 mb-4">Basic Information</h3>
          <div className="space-y-4">
            <Input label="Title" value="Machine Learning for Crop Yield Prediction in Nigeria" onChange={()=>{}} />
            <div className="flex flex-col space-y-1.5">
              <label className="text-sm font-medium text-slate-700">Abstract</label>
              <textarea className="px-3 py-2 border border-slate-300 rounded-md h-32 text-sm" defaultValue="This study applies random forest regressors to predict crop yields..." />
            </div>
            <Input label="Keywords" value="Machine Learning, Agriculture, Predictive Modeling" onChange={()=>{}} />
          </div>
        </Card>

        <Card className="p-6">
          <h3 className="text-lg font-medium text-slate-900 mb-4">External Links</h3>
          <div className="space-y-4">
            <Input label="GitHub / Source Code Repository" placeholder="https://github.com/..." />
            <Input label="Dataset Link (e.g., Kaggle, Mendeley Data)" placeholder="https://..." />
          </div>
        </Card>
      </div>
    </AuthenticatedLayout>
  );
};

export default Screen20EditThesis;
